"""FR #7410: bob.ntsa.uk /downloads page + latest MSI asset policy."""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

from repo_layout import REPO

WWW = REPO / "jeeves" / "www" / "irc-ntsa"
DOWNLOADS = WWW / "downloads"
INSTALL = REPO / "jeeves" / "scripts" / "Install-BobWebhooks.ps1"
SCRIPT = REPO / "common" / "scripts" / "bob_downloads_assets.py"


def _load_assets_mod():
    spec = importlib.util.spec_from_file_location("bob_downloads_assets", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_fr7410_downloads_index_exists_and_has_three_tiles():
    page = DOWNLOADS / "index.html"
    assert page.is_file(), "jeeves/www/irc-ntsa/downloads/index.html required for /downloads"
    text = page.read_text(encoding="utf-8")
    assert "Bob ear" in text
    assert "Jeeves" in text
    assert "airc" in text
    assert 'href="/downloads"' in text or 'aria-current="page"' in text
    # FR #7530: names come from the latest-release API, not a stamped version.
    assert "releases/latest" in text
    assert "/downloads/error.html" in text
    for product in ("bob", "jeeves", "airc"):
        assert f'data-product="{product}"' in text


def test_fr7410_download_link_patterns_match_asset_policy():
    text = (DOWNLOADS / "index.html").read_text(encoding="utf-8")
    assert "releases/latest/download/" in text
    assert "-latest.msi" in text
    for product in ("bob", "jeeves", "airc"):
        assert product + "-latest.msi" in text or f"'{product}'" in text or f'"{product}"' in text


def test_fr7410_site_css_tokens_present():
    css = WWW / "site.css"
    assert css.is_file()
    text = css.read_text(encoding="utf-8")
    for token in ("--ink", "--gold", "--charcoal", "--paper"):
        assert token in text


def test_fr7410_empty_and_error_states_shipped():
    for name in ("empty.html", "error.html"):
        p = DOWNLOADS / name
        assert p.is_file(), name
        t = p.read_text(encoding="utf-8")
        assert "Bob ear" in t
        assert "site.css" in t


def test_fr7410_home_has_downloads_nav_target():
    home = WWW / "index.html"
    text = home.read_text(encoding="utf-8")
    assert 'href="/downloads"' in text or 'href="/downloads/"' in text or 'href="downloads/"' in text


def test_fr7410_install_bobwebhooks_syncs_downloads():
    text = INSTALL.read_text(encoding="utf-8-sig")
    assert "downloads" in text.lower()
    assert "site.css" in text
    # Must copy the downloads tree (not only index.html)
    assert "downloads" in text and "Copy-Item" in text


def test_fr7410_resolver_prefers_latest_alias():
    mod = _load_assets_mod()
    payload = {
        "tag_name": "v9.9.9",
        "assets": [
            {"name": "bob-1.0.7.msi"},
            {"name": "bob-latest.msi"},
            {"name": "bob-latest.msi.sha256"},
            {"name": "jeeves-1.0.7.msi"},
            {"name": "airc-1.0.7.msi"},
        ],
    }
    resolved = mod.resolve_latest_assets(payload)
    assert resolved["bob"]["msi"] == "bob-latest.msi"
    assert resolved["bob"]["sha256"] == "bob-latest.msi.sha256"
    assert resolved["bob"]["url"].endswith("/bob-latest.msi")
    assert resolved["jeeves"]["msi"] == "jeeves-1.0.7.msi"
    assert resolved["airc"]["msi"] == "airc-1.0.7.msi"


def test_fr7410_resolver_versioned_when_no_alias():
    mod = _load_assets_mod()
    payload = {
        "tag_name": "v1.0.7",
        "assets": [
            {"name": "bob-1.0.6.msi"},
            {"name": "bob-1.0.7.msi"},
            {"name": "bob-1.0.7.msi.sha256"},
            {"name": "jeeves-1.0.7.msi"},
            {"name": "airc-network-installer-1.0.7.exe"},
            {"name": "airc-1.0.7.msi"},
        ],
    }
    resolved = mod.resolve_latest_assets(payload)
    assert resolved["bob"]["msi"] == "bob-1.0.7.msi"
    assert resolved["bob"]["sha256"] == "bob-1.0.7.msi.sha256"
    assert resolved["airc"]["msi"] == "airc-1.0.7.msi"
    assert "network-installer" not in (resolved["airc"]["msi"] or "")


def test_fr7410_resolver_missing_product():
    mod = _load_assets_mod()
    resolved = mod.resolve_latest_assets({"tag_name": "v0", "assets": [{"name": "bob-1.0.0.msi"}]})
    assert resolved["bob"]["msi"] == "bob-1.0.0.msi"
    assert resolved["jeeves"]["msi"] is None
    assert resolved["airc"]["url"] is None
