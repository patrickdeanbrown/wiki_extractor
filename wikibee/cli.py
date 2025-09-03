from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, cast

import click
import requests
import typer
from rich.console import Console
from typer.core import TyperGroup

from . import config  # re-exported for tests to monkeypatch
from . import formatting as _formatting
from ._types import ExtractsResponse, PageObject, SearchResult
from .client import WikiClient
from .tts_normalizer import normalize_for_tts as tts_normalize_for_tts
from .tts_openai import TTSClientError, TTSOpenAIClient

# Re-export frequently used formatting helpers for backward compatibility.
# Import the module and assign names so linters don't report unused imports.
sanitize_filename = _formatting.sanitize_filename
normalize_for_tts = _formatting.normalize_for_tts
make_tts_friendly = _formatting.make_tts_friendly
INFLECT_AVAILABLE = _formatting.INFLECT_AVAILABLE
write_text_file = _formatting.write_text_file

logger = logging.getLogger(__name__)


class _DefaultGroup(TyperGroup):
    """Click Group that treats non-command first argument as default command.

    This lets `wikibee <article> [options]` work alongside subcommands
    like `wikibee config init`.
    """

    default_command_name = "main"

    def resolve_command(
        self, ctx: click.Context, args: List[str]
    ) -> Tuple[Optional[str], click.Command | None, List[str]]:
        if (
            args
            and args[0] not in self.commands
            and self.default_command_name in self.commands
        ):
            # Prepend the default command name so click routes properly
            args = [self.default_command_name] + args
        return super().resolve_command(ctx, args)


app = typer.Typer(cls=_DefaultGroup)
console = Console()

DEFAULTS: Dict[str, object] = {
    # CLI/config defaults (CLI args override these; config can override defaults)
    "timeout": 15,
    "lead_only": False,
    "tts_voice": "af_sky+af_bella",
    "tts_format": "mp3",
    "tts_server": "http://localhost:8880/v1",
}


@dataclass
class Args:
    article: str
    output_dir: str
    filename: Optional[str]
    no_save: bool
    timeout: int
    lead_only: bool
    tts_file: bool
    heading_prefix: Optional[str]
    verbose: bool
    tts_audio: bool
    tts_server: str
    tts_voice: Optional[str]
    tts_format: str
    yolo: bool
    tts_normalize: bool


def _handle_search(search_term: str, args: Args) -> Optional[str]:
    """Handle search term input and return selected article URL."""
    client = WikiClient()

    try:
        results = client.search_articles(search_term, limit=10, timeout=args.timeout)
    except requests.exceptions.RequestException as e:
        console.print(f"[red]Search failed: {e}[/]")
        return None

    if not results:
        console.print(f"[yellow]No results found for '{search_term}'[/]")
        console.print("[cyan]Try different search terms or check spelling.[/]")
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


def _show_search_menu(results: List[SearchResult], search_term: str) -> Optional[str]:
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


def _process_page(
    p: PageObject, convert_numbers_for_tts: bool, raise_on_error: bool
) -> Tuple[Optional[str], Optional[str]]:
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
    session: Optional[requests.Session] = None,
    raise_on_error: bool = False,
) -> Tuple[Optional[str], Optional[str]]:
    final_page_title: Optional[str] = None

    client = WikiClient(session)

    title = _parse_title(url)

    try:
        data: ExtractsResponse = client.fetch_page(url, title, lead_only, timeout)
    except requests.exceptions.RequestException as e:
        logger.error("Network error: %s", e)
        if raise_on_error:
            raise NetworkError(e)
        return None, final_page_title
    except json.JSONDecodeError as e:
        logger.error("API returned invalid JSON: %s", e)
        if raise_on_error:
            raise APIError(e)
        return None, final_page_title

    pages = (data.get("query") or {}).get("pages") or {}
    if not pages:
        logger.warning("No pages found in API response")
        return None, final_page_title

    page_obj = next(iter(pages.values()))
    return _process_page(page_obj, convert_numbers_for_tts, raise_on_error)


@app.command()
def main(
    article: str = typer.Argument(..., help="Wikipedia article URL or search term"),
    output_dir: str = typer.Option(
        os.path.join(os.getcwd(), "output"),
        "-o",
        "--output",
        "--output-dir",
        help="Directory to save output",
    ),
    filename: Optional[str] = typer.Option(
        None,
        "-f",
        "--filename",
        help="Base filename to use (otherwise derived from title)",
    ),
    no_save: bool = typer.Option(
        False,
        "-n",
        "--no-save",
        help="Do not save to file; print to stdout",
    ),
    timeout: int = typer.Option(
        15,
        "-t",
        "--timeout",
        help="HTTP timeout seconds",
    ),
    lead_only: bool = typer.Option(
        False,
        "-l",
        "--lead-only",
        help="Fetch only the lead (intro) section",
    ),
    tts: bool = typer.Option(
        False,
        "--tts",
        "--tts-file",
        help="Also produce a TTS-friendly .txt alongside the .md",
    ),
    heading_prefix: Optional[str] = typer.Option(
        None,
        "--heading-prefix",
        help="Prefix for headings in TTS file, e.g. 'Section:'",
    ),
    verbose: bool = typer.Option(
        False,
        "-v",
        "--verbose",
        help="Verbose logging",
    ),
    audio: bool = typer.Option(
        False,
        "--audio",
        "--tts-audio",
        help="Also produce an audio file via the local Kokoro/OpenAI-compatible TTS",
    ),
    tts_server: str = typer.Option(
        "http://localhost:8880/v1",
        "--tts-server",
        help="Base URL of the local TTS server (OpenAI-compatible)",
    ),
    tts_voice: Optional[str] = typer.Option(
        None,
        "--tts-voice",
        help="Voice identifier for the TTS engine",
    ),
    tts_format: str = typer.Option(
        "mp3",
        "--tts-format",
        help="Audio output format",
    ),
    yolo: bool = typer.Option(
        False,
        "-y",
        "--yolo",
        help="Auto-select first search result without prompting",
    ),
    tts_normalize: bool = typer.Option(
        False,
        "--tts-normalize",
        help=(
            "Apply text normalization for better TTS pronunciation "
            "(e.g., 'Richard III' → 'Richard the third')"
        ),
    ),
) -> None:
    args = Args(
        article=article,
        output_dir=output_dir,
        filename=filename,
        no_save=no_save,
        timeout=timeout,
        lead_only=lead_only,
        tts_file=tts,
        heading_prefix=heading_prefix,
        verbose=verbose,
        tts_audio=audio,
        tts_server=tts_server,
        tts_voice=tts_voice,
        tts_format=tts_format,
        yolo=yolo,
        tts_normalize=tts_normalize,
    )

    # Merge configuration precedence: DEFAULTS < config file < CLI args (None ignored)
    cfg = config.load_config()
    cli_overrides: Dict[str, object] = {
        "timeout": timeout,
        "lead_only": lead_only,
        "tts_voice": tts_voice,  # may be None if not provided explicitly
        "tts_format": tts_format,
        "tts_server": tts_server,
    }
    merged = config.merge_configs(DEFAULTS, cfg, cli_overrides)
    # Apply merged values back onto args used downstream
    args.timeout = int(merged.get("timeout", args.timeout))
    args.lead_only = bool(merged.get("lead_only", args.lead_only))
    args.tts_voice = cast(Optional[str], merged.get("tts_voice", args.tts_voice))
    args.tts_format = cast(str, merged.get("tts_format", args.tts_format))
    args.tts_server = cast(str, merged.get("tts_server", args.tts_server))

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
        url_opt = _handle_search(article_input, args)
        if url_opt is None:
            raise typer.Exit(code=1)
        url = url_opt
        logger.info("Extracting article: %s", url)

    result_text, page_title = extract_wikipedia_text(
        url,
        convert_numbers_for_tts=False,
        timeout=args.timeout,
        lead_only=args.lead_only,
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
    args: Args,
) -> None:
    audio_ext = "." + args.tts_format
    audio_path = os.path.splitext(md_path)[0] + audio_ext
    text_source = _build_tts_text(markdown_content, args)
    try:
        saved = _synthesize_audio(text_source, audio_path, out_dir, args)
        logger.info("Saved audio to %s", saved)
        console.print(f"Audio saved to: {saved}")
    except TTSClientError as e:
        logger.error("Failed to synthesize audio: %s", e)


def _build_tts_text(markdown_content: str, args: Args) -> str:
    # Apply TTS normalization if requested
    if args.tts_normalize:
        normalized_content = tts_normalize_for_tts(markdown_content)
    else:
        normalized_content = markdown_content

    # Apply TTS-friendly formatting
    if args.tts_file:
        return make_tts_friendly(normalized_content, heading_prefix=args.heading_prefix)
    return make_tts_friendly(normalized_content)


def _synthesize_audio(text: str, audio_path: str, out_dir: str, args: Args) -> str:
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
    args: Args,
    markdown_content: str,
    md_path: str,
    out_dir: str,
    page_title: Optional[str],
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


# -----------------
# Config subcommands
# -----------------
config_app = typer.Typer(help="Manage wikibee configuration")


def _toml_dump_simple(data: Dict[str, object]) -> str:
    lines: List[str] = []
    for k, v in data.items():
        if isinstance(v, bool):
            val = "true" if v else "false"
        elif isinstance(v, (int, float)):
            val = str(v)
        else:
            s = str(v)
            s = s.replace("\\", "\\\\").replace('"', '\\"')
            val = f'"{s}"'
        lines.append(f"{k} = {val}")
    return "\n".join(lines) + "\n"


@config_app.command("init")
def config_init(
    force: bool = typer.Option(False, "--force", help="Overwrite if exists")
) -> None:
    """Create a default config file at the standard location."""
    path = config.get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        console.print(
            f"[yellow]Config already exists at {path}. Use --force to overwrite.[/]"
        )
        raise typer.Exit(code=1)

    defaults = {k: v for k, v in DEFAULTS.items() if v is not None}
    content = _toml_dump_simple(defaults)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    console.print(f"Default configuration file created at {path}")


app.add_typer(config_app, name="config")

if __name__ == "__main__":
    app()
