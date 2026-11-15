"""FR #7649: downloads pages have no double space in visible text."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGES = [
    ROOT / "jeeves" / "www" / "irc-ntsa" / "downloads" / "index.html",
    ROOT / "jeeves" / "www" / "irc-ntsa" / "downloads" / "empty.html",
    ROOT / "jeeves" / "www" / "irc-ntsa" / "downloads" / "error.html",
]
_TAG = re.compile(r"<[^>]+>")


def _visible_chunks(html: str) -> list[str]:
    html = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.I)
    html = re.sub(r"<style[\s\S]*?</style>", "", html, flags=re.I)
    chunks = []
    for part in _TAG.split(html):
        text = part.strip()
        if text:
            chunks.append(text)
    return chunks


def test_fr7649_downloads_visible_text_has_no_double_space():
    for path in PAGES:
        for chunk in _visible_chunks(path.read_text(encoding="utf-8")):
            assert "  " not in chunk, f"{path.name} has a double space in {chunk!r}"
    error = PAGES[2].read_text(encoding="utf-8")
    assert "Could not load the download links right now." in error
    assert "Could not resolve" not in error
