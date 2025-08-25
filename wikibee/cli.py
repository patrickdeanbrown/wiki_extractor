from __future__ import annotations

import json
import logging
import os
from types import SimpleNamespace
from typing import Optional, Tuple

import requests
import typer
from rich.console import Console

from . import formatting as _formatting
from .client import WikiClient
from .tts_normalizer import normalize_for_tts as tts_normalize_for_tts
from .tts_openai import TTSClientError, TTSOpenAIClient
from .config import load_config # New import

# Re-export frequently used formatting helpers for backward compatibility.
# Import the module and assign names so linters don't report unused imports.
sanitize_filename = _formatting.sanitize_filename
normalize_for_tts = _formatting.normalize_for_tts
make_tts_friendly = _formatting.make_tts_friendly
INFLECT_AVAILABLE = _formatting.INFLECT_AVAILABLE
write_text_file = _formatting.write_text_file

logger = logging.getLogger(__name__)

app = typer.Typer()
console = Console()


def _handle_search(search_term: str, args) -> Optional[str]:
    """Handle search term input and return selected article URL."""
    client = WikiClient()

    try:
        # Updated limit
        results = client.search_articles(
            search_term, limit=args.search_limit, timeout=args.timeout
        )
    except requests.exceptions.RequestException as e: # type: ignore[name-defined]
        console.print(f"[red]Search failed: {e}[/]")
        return None

    if not results:
        console.print(f"[yellow]No results found for '{search_term}'")
        console.print("[cyan]Try different search terms or check spelling.")
        return None

    if len(results) == 1:
        result = results[0]
        console.print(f"[green]Found exact match: \"{result['title']}\"[/]")
        console.print("[cyan]Extracting article...[/]")
        return result["url"]

    # Multiple results - show menu unless --yolo
    if args.yolo:
        result = results[0]
        console.print(f"[magenta]Auto-selected: \"{result['title']}\"[/]")
        return result["url"]

    return _show_search_menu(results, search_term)


def _show_search_menu(results: list[dict], search_term: str) -> Optional[str]:
    """Display interactive search menu and return selected URL."""
    console.print(
        f"\n[bold blue]Found {len(results)} results for '{search_term}':[/]\n"
    )

    for i, result in enumerate(results, 1):
        title = result["title"]
        desc = result.get("description", "").strip()

        # Highlight first result and number others
        if i == 1:
            console.print(f"[bold green]1. {title}[/]")
        else:
            console.print(f"[bold]{i}. {title}[/]")

        if desc:
            console.print(f"   [cyan]{desc}[/]")
        console.print()

    while True:
        try:
            prompt = f"[yellow]Enter your choice (1-{len(results)}) or 'q' to quit: [/]"
            choice = console.input(prompt).strip().lower()

            if choice == "q":
                console.print("[magenta]Cancelled[/]")
                return None

            choice_num = int(choice)
            if 1 <= choice_num <= len(results):
                selected = results[choice_num - 1]
                console.print(f"[green]Selected: {selected['title']}[/]")
                return selected["url"]
            else:
                console.print(
                    f"[red]Please enter a number between 1 and {len(results)}[/]"
                )
        except ValueError:
            console.print("[red]Please enter a valid number or 'q' to quit[/]")
        except KeyboardInterrupt:
            console.print("\n[magenta]Cancelled[/]")
            return None


# Structured exceptions
class NetworkError(RuntimeError):
    """Network-related errors (requests exceptions)"""


class APIError(RuntimeError):
    """API returned invalid data or JSON decoding failed"""


class NotFoundError(RuntimeError):
    """Page not found or no extract available"""


class DisambiguationError(RuntimeError):
    """Raised when the requested title is a disambiguation page."""


def _parse_title(u: str) -> str:
    from urllib.parse import unquote, urlparse

    parsed = urlparse(u)
    if not parsed.scheme:
        raise ValueError("URL must include scheme (http:// or https://)")

    path = parsed.path or ""
    wiki_prefix = "/wiki/"
    title = None
    if wiki_prefix in path:
        title = path.split(wiki_prefix, 1)[1]
    else:
        if path and path.strip("/"):
            title = path.strip("/").split("/")[-1]

    if title:
        return unquote(title)
    raise ValueError("Could not determine page title from URL")


def _process_page(p: dict, convert_numbers_for_tts: bool, raise_on_error: bool):
    pageprops = p.get("pageprops") or {}
    if "disambiguation" in pageprops:
        final_title = p.get("title")
        logger.info("Disambiguation page detected for: %s", final_title)
        if raise_on_error:
            raise DisambiguationError(f"Title '{final_title}' is a disambiguation page")
        return None, final_title

    final_title = p.get("title")
    extract_text = p.get("extract")
    if extract_text is None:
        logger.warning("No extract text present for page: %s", final_title)
        if raise_on_error:
            raise NotFoundError(f"No extract text present for page: {final_title}")
        return None, final_title

    out_text = normalize_for_tts(extract_text, convert_numbers=convert_numbers_for_tts)
    return out_text, final_title


def extract_wikipedia_text(
    url: str,
    convert_numbers_for_tts: bool = False,
    timeout: int = 15,
    lead_only: bool = False,
    session: Optional[object] = None,
    raise_on_error: bool = False,
    retries: int = 3,
) -> Tuple[Optional[str], Optional[str]]:
    final_page_title: Optional[str] = None

    client = WikiClient(session, retries=retries)

    title = _parse_title(url)

    try:
        data = client.fetch_page(url, title, lead_only, timeout)
    except requests.exceptions.RequestException as e:  # type: ignore[name-defined]
        logger.error("Network error: %s", e)
        if raise_on_error:
            raise NetworkError(e)
        return None, final_page_title
    except json.JSONDecodeError as e:
        logger.error("API returned invalid JSON: %s", e)
        if raise_on_error:
            raise APIError(e)
        return None, final_page_title

    pages = data.get("query", {}).get("pages", {})
    if not pages:
        logger.warning("No pages found in API response")
        return None, final_page_title

    page_obj = next(iter(pages.values()))
    return _process_page(page_obj, convert_numbers_for_tts, raise_on_error)


@app.command()
def main(
    article: str = typer.Argument(..., help="Wikipedia article URL or search term"),
    output_dir: Optional[str] = typer.Option(
        None,
        "-o",
        "--output",
        "--output-dir",
        help="Directory to save output",
        envvar="WIKIBEE_OUTPUT_DIR",
    ),
    filename: Optional[str] = typer.Option(
        None,
        "-f",
        "--filename",
        help="Base filename to use (otherwise derived from title)",
    ),
    no_save: Optional[bool] = typer.Option(
        None,
        "-n",
        "--no-save",
        help="Do not save to file; print to stdout",
    ),
    timeout: Optional[int] = typer.Option(
        None,
        "-t",
        "--timeout",
        help="HTTP timeout seconds",
        envvar="WIKIBEE_TIMEOUT",
    ),
    lead_only: Optional[bool] = typer.Option(
        None,
        "-l",
        "--lead-only",
        help="Fetch only the lead (intro) section",
    ),
    tts: Optional[bool] = typer.Option(
        None,
        "--tts",
        "--tts-file",
        help="Also produce a TTS-friendly .txt alongside the .md",
    ),
    heading_prefix: Optional[str] = typer.Option(
        None,
        "--heading-prefix",
        help="Prefix for headings in TTS file, e.g. 'Section:'",
    ),
    verbose: Optional[bool] = typer.Option(
        None,
        "-v",
        "--verbose",
        help="Verbose logging",
    ),
    audio: Optional[bool] = typer.Option(
        None,
        "--audio",
        "--tts-audio",
        help="Also produce an audio file via the local Kokoro/OpenAI-compatible TTS",
    ),
    tts_server: Optional[str] = typer.Option(
        None,
        "--tts-server",
        help="Base URL of the local TTS server (OpenAI-compatible)",
        envvar="WIKIBEE_TTS_SERVER",
    ),
    tts_voice: Optional[str] = typer.Option(
        None,
        "--tts-voice",
        help="Voice identifier for the TTS engine",
        envvar="WIKIBEE_TTS_VOICE",
    ),
    tts_format: Optional[str] = typer.Option(
        None,
        "--tts-format",
        help="Audio output format",
    ),
    yolo: Optional[bool] = typer.Option(
        None,
        "-y",
        "--yolo",
        help="Auto-select first search result without prompting",
    ),
    tts_normalize: Optional[bool] = typer.Option(
        None,
        "--tts-normalize",
        help=(
            "Apply text normalization for better TTS pronunciation "
            "(e.g., 'Richard III' → 'Richard the third')"
        ),
    ),
    search_limit: Optional[int] = typer.Option(
        None,
        "--search-limit",
        help="Control how many search results to show",
    ),
    retries: Optional[int] = typer.Option(
        None,
        "--retries",
        help="Number of retry attempts for failed requests",
    ),
):
    # Load configuration from file
    config = load_config()

    # Resolve final values based on precedence:
    # CLI > Env Var (Typer handles) > Config File > Hardcoded Default
    final_output_dir = output_dir or config.get(
        "general", "output_dir", os.path.join(os.getcwd(), "output")
    )
    final_filename = filename
    final_no_save = (
        no_save if no_save is not None else config.get("general", "no_save", False)
    )
    final_timeout = timeout or config.get("general", "timeout", 15)
    final_lead_only = (
        lead_only
        if lead_only is not None
        else config.get("general", "lead_only", False)
    )
    final_tts = tts if tts is not None else config.get("general", "tts", False)
    final_heading_prefix = heading_prefix or config.get(
        "general", "heading_prefix", None
    )
    final_verbose = (
        verbose if verbose is not None else config.get("general", "verbose", False)
    )
    final_audio = audio if audio is not None else config.get("general", "audio", False)
    final_tts_server = tts_server or config.get("tts", "server_url", "http://localhost:8880/v1")
    final_tts_voice = tts_voice or config.get("tts", "default_voice", "af_sky+af_bella")
    final_tts_format = tts_format or config.get("tts", "format", "mp3")
    final_yolo = (
        yolo if yolo is not None else config.get("general", "auto_select", False)
    )
    final_tts_normalize = (
        tts_normalize
        if tts_normalize is not None
        else config.get("general", "tts_normalize", False)
    )
    final_search_limit = search_limit or config.get("search", "search_limit", 10)
    final_retries = retries or config.get("general", "retries", 3)

    args = SimpleNamespace(
        article=article,
        output_dir=final_output_dir,
        filename=final_filename,
        no_save=final_no_save,
        timeout=final_timeout,
        lead_only=final_lead_only,
        tts_file=final_tts,
        heading_prefix=final_heading_prefix,
        verbose=final_verbose,
        tts_audio=final_audio,
        tts_server=final_tts_server,
        tts_voice=final_tts_voice,
        tts_format=final_tts_format,
        yolo=final_yolo,
        tts_normalize=final_tts_normalize,
        search_limit=final_search_limit,
        retries=final_retries,
    )

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    article_input = args.article

    # Determine if input is URL or search term
    if article_input.startswith(("http://", "https://")):
        # It's a URL - proceed with existing logic
        url = article_input
        logger.info("Attempting to extract text from: %s", url)
    else:
        # It's a search term - perform search first
        url = _handle_search(article_input, args)
        if url is None:
            raise typer.Exit(code=1)
        logger.info("Extracting article: %s", url)

    result_text, page_title = extract_wikipedia_text(
        url,
        convert_numbers_for_tts=False,
        timeout=args.timeout,
        lead_only=args.lead_only,
        retries=args.retries, # Added retries
    )

    if result_text is None:
        logger.error("Failed to extract text from URL")
        raise typer.Exit(code=1)

    base_name = args.filename or page_title or "wikipedia_article"
    safe_base = sanitize_filename(base_name)
    md_name = safe_base + ".md"
    out_dir = os.path.abspath(args.output_dir)
    os.makedirs(out_dir, exist_ok=True)

    md_path = os.path.join(out_dir, md_name)
    if os.path.exists(md_path):
        for i in range(1, 1000):
            candidate = os.path.join(out_dir, f"{safe_base}_{i}.md")
            if not os.path.exists(candidate):
                md_path = candidate
                break

    markdown_content = f"# {page_title}\n\n{result_text}\n"
    try:
        _write_outputs(args, markdown_content, md_path, out_dir, page_title)
    except IOError as e:
        logger.error("Failed to write output: %s", e)


def _produce_audio(
    markdown_content: str,
    md_path: str,
    out_dir: str,
    args,
):
    audio_ext = "." + args.tts_format
    audio_path = os.path.splitext(md_path)[0] + audio_ext
    text_source = _build_tts_text(markdown_content, args)
    try:
        saved = _synthesize_audio(text_source, audio_path, out_dir, args)
        logger.info("Saved audio to %s", saved)
        console.print(f"Audio saved to: {saved}")
    except TTSClientError as e:
        logger.error("Failed to synthesize audio: %s", e)


def _build_tts_text(markdown_content: str, args) -> str:
    # Apply TTS normalization if requested
    if args.tts_normalize:
        normalized_content = tts_normalize_for_tts(markdown_content)
    else:
        normalized_content = markdown_content

    # Apply TTS-friendly formatting
    if args.tts_file:
        return make_tts_friendly(normalized_content, heading_prefix=args.heading_prefix)
    return make_tts_friendly(normalized_content)


def _synthesize_audio(text: str, audio_path: str, out_dir: str, args) -> str:
    tts_client = TTSOpenAIClient(base_url=args.tts_server)
    return tts_client.synthesize_to_file(
        text,
        dest_path=audio_path,
        base_dir=out_dir,
        model="kokoro",
        voice=args.tts_voice,
        file_format=args.tts_format,
    )


def _write_outputs(
    args,
    markdown_content: str,
    md_path: str,
    out_dir: str,
    page_title: str,
) -> None:
    """Write markdown and optional TTS text/audio outputs."""
    if args.no_save:
        console.print(markdown_content)
        return

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)
    logger.info("Saved markdown to %s", md_path)
    console.print(f"Output saved to: {md_path}")

    if args.tts_file:
        # Apply normalization if requested
        if args.tts_normalize:
            content_for_tts = tts_normalize_for_tts(markdown_content)
        else:
            content_for_tts = markdown_content
        tts_text = make_tts_friendly(
            content_for_tts, heading_prefix=args.heading_prefix
        )
        tts_path = os.path.splitext(md_path)[0] + ".txt"
        with open(tts_path, "w", encoding="utf-8") as f:
            f.write(tts_text)
        logger.info("Saved TTS-friendly text to %s", tts_path)
        console.print(f"TTS-friendly copy saved to: {tts_path}")

    if args.tts_audio:
        _produce_audio(markdown_content, md_path, out_dir, args)


if __name__ == "__main__":
    app()
