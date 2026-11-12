"""MRB #6780 hostile pins for FR #6756 shared shell / logo."""
from __future__ import annotations

from pathlib import Path

import jeeves_settings_http as http


def test_mrb6780_pack_logo_fallback_when_tray_missing(tmp_path, monkeypatch):
    missing = tmp_path / "no-tray.png"
    pack = (
        Path(__file__).resolve().parents[2]
        / "jeeves"
        / "docs"
        / "appliance-ui-20261112"
        / "mocks"
        / "ntsa-gut-logo.png"
    )
    assert pack.is_file()
    monkeypatch.setattr(http, "_TRAY_LOGO", missing)
    monkeypatch.setattr(http, "_PACK_LOGO", pack)
    assert http.ntsa_gut_logo_path() == pack


def test_mrb6780_login_shell_omits_nav_links():
    html = http._render_login_html()
    assert "/assets/ntsa-gut-logo.png" in html
    assert "<header>" in html
    assert 'href="/logout"' not in html
    assert "User name" in html
    assert 'name="account"' in html
