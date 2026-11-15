"""FR #7456: /downloads airc card has PowerShell install snippet + copy button."""
from __future__ import annotations

import re
from pathlib import Path

from repo_layout import REPO

PAGE = REPO / "jeeves" / "www" / "irc-ntsa" / "downloads" / "index.html"

_SECRET_MARKERS = (
    "password=",
    "Bearer ",
    "github_pat_",
    "ghs_",
    "console.password",
    "AIRC_PACK_ERGO",
)


def _airc_card(html: str) -> str:
    m = re.search(
        r'<article\s+class="card"\s+data-product="airc">(.*?)</article>',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    assert m, "airc card missing"
    return m.group(1)


def test_fr7456_airc_card_has_snippet_and_copy_button():
    html = PAGE.read_text(encoding="utf-8")
    card = _airc_card(html)
    assert 'data-role="install-snippet"' in card
    assert 'data-role="copy-install"' in card
    assert "Copy" in card
    assert "Elevated" in card or "elevated" in card
    assert "msiexec" in card
    assert "AIRC_PROFILE=client" in card
    assert "Get-Service Airc" in card
    assert "/qn" in card


def test_fr7456_snippet_msi_url_matches_download_link():
    html = PAGE.read_text(encoding="utf-8")
    card = _airc_card(html)
    msi = re.search(
        r'data-role="msi"\s+href="([^"]+\.msi)"',
        card,
        re.IGNORECASE,
    )
    assert msi, "airc download MSI link missing"
    url = msi.group(1)
    assert f"$msiUrl = '{url}'" in card or f'$msiUrl = "{url}"' in card
    assert "airc" in url.lower() and url.lower().endswith(".msi")


def test_fr7456_snippet_has_no_secret_looking_values():
    html = PAGE.read_text(encoding="utf-8")
    card = _airc_card(html)
    low = card.lower()
    for marker in _SECRET_MARKERS:
        assert marker.lower() not in low, marker
    # Property name AIRC_PROFILE is OK; values must not look like tokens.
    assert re.search(r"AIRC_PROFILE\s*=\s*client\b", card)
    assert not re.search(r"AIRC_PROFILE\s*=\s*['\"]?[A-Za-z0-9_\-]{40,}", card)
