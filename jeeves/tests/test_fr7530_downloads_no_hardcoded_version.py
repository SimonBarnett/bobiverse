"""FR #7530: /downloads must not stamp a semver; lookup failure stays on-page (FR #8759)."""
from __future__ import annotations

import re
from pathlib import Path

from repo_layout import REPO

DOWNLOADS = REPO / "jeeves" / "www" / "irc-ntsa" / "downloads"
MOCK = REPO / "jeeves" / "docs" / "mocks" / "bob-ntsa-public-front-door" / "downloads.html"
_VER = re.compile(r"\d+\.\d+\.\d+")


def test_fr7530_downloads_html_and_js_have_no_semver():
    files = list(DOWNLOADS.glob("*.html")) + list(DOWNLOADS.glob("*.js"))
    assert files
    if MOCK.is_file():
        files.append(MOCK)
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert _VER.search(text) is None, f"{path.name} stamps a version"


def test_fr7530_lookup_failure_stays_on_page_with_per_card_errors():
    """FR #7530 + #8759: no stamped semver; fail path marks cards, does not redirect."""
    text = (DOWNLOADS / "index.html").read_text(encoding="utf-8")
    assert "api.github.com/repos/SimonBarnett/bobiverse/releases/latest" in text
    assert "window.location.href = '/downloads/error.html'" not in text
    assert "markCardUnavailable" in text
    assert "id=\"release-tag\"" in text
    assert "payload.tag_name" in text
