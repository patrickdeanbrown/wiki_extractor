from __future__ import annotations

import re
from typing import Any, Iterable, Match, Optional
from urllib.parse import unquote

try:
    import inflect as _inflect

    _INFLECT_ENGINE: Any = _inflect.engine()
    INFLECT_AVAILABLE = True
except Exception:
    _INFLECT_ENGINE = None
    INFLECT_AVAILABLE = False


def sanitize_filename(name: str, max_len: int = 100) -> str:
    if not name:
        return "wikipedia_article"

    try:
        name = unquote(name)
    except Exception:
        pass

    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r"\s+", "_", name)
    name = name.strip(" .")

    if not name:
        name = "wikipedia_article"

    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    if name.upper() in reserved:
        name = name + "_file"

    if len(name) > max_len:
        root, dot, ext = name.rpartition(".")
        if dot and root and len(ext) < 10:
            keep = max_len - (len(ext) + 1)
            name = root[:keep].rstrip("_") + "." + ext
        else:
            name = name[:max_len].rstrip("_")

    return name


def normalize_for_tts(text: str, convert_numbers: bool = False) -> str:
    if not text:
        return ""

    text = text.strip()
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    text = re.sub(r"^\s*[\*#]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^==+\s*(.*?)\s*==+\s*$", "", text, flags=re.MULTILINE).strip()

    if convert_numbers and INFLECT_AVAILABLE:
        try:
            import inflect

            p = inflect.engine()

            def _repl(m: Match[str]) -> str:
                return str(p.number_to_words(m.group(1)))

            text = re.sub(r"\b(\d+)\b", _repl, text)
        except Exception:
            pass

    return text.strip()


def make_tts_friendly(markdown: str, heading_prefix: Optional[str] = None) -> str:
    out_lines: list[str] = []
    for line in markdown.splitlines():
        m = re.match(r"^\s*(?P<hashes>#+)\s*(?P<title>.+?)\s*$", line)
        if m:
            title = m.group("title").strip()
            if heading_prefix:
                out_lines.append(f"{heading_prefix} {title}.")
            else:
                out_lines.append(f"{title}.")
            continue

        line = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", line)
        line = re.sub(r"[*_]{1,3}(.+?)[*_]{1,3}", r"\1", line)
        line = re.sub(r"`(.+?)`", r"\1", line)
        line = re.sub(r"^\s*#+\s*", "", line)
        out_lines.append(line)

    text = "\n".join(out_lines)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip() + "\n"
    return text


def write_text_file(path: str, base_dir: str, content: str) -> None:
    """Safely write a text file ensuring it stays within base_dir.

    Raises ValueError if the resolved path is outside `base_dir` to avoid
    path traversal attacks.
    """
    import os

    base_dir = os.path.abspath(base_dir)
    target = os.path.abspath(path)
    if not (target == base_dir or target.startswith(base_dir + os.sep)):
        raise ValueError("Attempt to write outside of output directory")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(content)


def write_binary_file(
    path: str, base_dir: str, content_iterable: Iterable[bytes]
) -> None:
    """Safely write binary content to a path inside base_dir.

    `content_iterable` should yield bytes-like chunks (an iterable or generator).
    """
    import os

    base_dir = os.path.abspath(base_dir)
    target = os.path.abspath(path)
    if not (target == base_dir or target.startswith(base_dir + os.sep)):
        raise ValueError("Attempt to write outside of output directory")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as f:
        for chunk in content_iterable:
            if chunk:
                f.write(chunk)
