"""FR #7644: downloads cards and footer use plain English, not fleet jargon."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGES = [
    ROOT / "jeeves" / "www" / "irc-ntsa" / "downloads" / "index.html",
    ROOT / "jeeves" / "www" / "irc-ntsa" / "downloads" / "empty.html",
    ROOT / "jeeves" / "www" / "irc-ntsa" / "downloads" / "error.html",
    ROOT / "jeeves" / "docs" / "mocks" / "bob-ntsa-public-front-door" / "downloads.html",
]
BANNED = (
    "chair",
    "ear +",
    "shop",
    "title match",
    "asset match",
    "non-prerelease",
    "fleet ear",
    "chair service",
    "fleet boxes",
    "asset policy",
)
NEED = (
    "Install it on every worker machine",
    "Install it on the hub machine that serves this site",
    "run it on the PC where you do that work",
    "Install it on the machines that need that console",
)


def test_fr7644_pages_drop_jargon_and_say_who_and_where():
    for path in PAGES:
        text = path.read_text(encoding="utf-8")
        low = text.lower()
        for word in BANNED:
            assert word not in low, f"{path.name} still has {word!r}"
        for sentence in NEED:
            assert sentence in text, f"{path.name} missing {sentence!r}"
    index = PAGES[0].read_text(encoding="utf-8")
    mock = PAGES[3].read_text(encoding="utf-8")
    footer = "checksum file when one is published"
    assert footer in index
    assert footer in mock
    assert "{product}-latest.msi" not in index
