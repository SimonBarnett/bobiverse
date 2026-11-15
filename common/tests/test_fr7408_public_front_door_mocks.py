"""FR #7408: public front-door mocks + tokens + nav."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOCKS = ROOT / "jeeves" / "docs" / "mocks" / "bob-ntsa-public-front-door"
WWW_CSS = ROOT / "jeeves" / "www" / "site.css"
FR_MD = ROOT / "jeeves" / "docs" / "feature-request-bob-ntsa-public-front-door-2026-11-15.md"


def test_fr7408_required_mocks_and_tokens():
    assert (MOCKS / "site.css").is_file()
    assert WWW_CSS.is_file()
    css = (MOCKS / "site.css").read_text(encoding="utf-8")
    for token in ("--ink", "--gold", "--charcoal"):
        assert token in css, token
    for name in ("home.html", "empty.html", "error.html", "downloads.html", "jeeves-commands.html", "mcp-home.html"):
        assert (MOCKS / name).is_file(), name


def test_fr7408_home_nav_links():
    home = (MOCKS / "home.html").read_text(encoding="utf-8")
    assert "Downloads" in home
    assert "Jeeves" in home
    assert "MCP" in home
    assert "GitHub" in home
    assert "downloads.html" in home
    assert "jeeves-commands.html" in home
    assert "mcp-home.html" in home
    assert "github.com/SimonBarnett/bobiverse" in home


def test_fr7408_fr_pack_mentions_contrast_and_success():
    text = FR_MD.read_text(encoding="utf-8")
    assert "FR #7408" in text or "#7408" in text
    assert "## Success" in text
    assert "S1" in text and "S10" in text
    assert "400px" in text or "≤400" in text or "<=400" in text
    assert "charcoal" in text.lower() and "gold" in text.lower()