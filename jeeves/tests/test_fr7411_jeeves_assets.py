"""FR #7411: /jeeves asset URLs, pack-layout ico, IIS static map, no 404."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import bobcallback
import jeeves_settings_http as http
from repo_layout import REPO

SCRIPT = REPO / "jeeves" / "scripts" / "Install-BobWebhooks.ps1"
PS = shutil.which("powershell") or shutil.which("pwsh")
NEED_PS = pytest.mark.skipif(not PS, reason="powershell or pwsh required")
ICO = REPO / "jeeves" / "assets" / "jeeves-butler.ico"


def test_fr7411_ui_href_asset_url_construction():
    assert http.ui_href("", "/assets/jeeves-butler.ico") == "/assets/jeeves-butler.ico"
    assert (
        http.ui_href("/jeeves", "/assets/jeeves-butler.ico")
        == "/jeeves/assets/jeeves-butler.ico"
    )
    assert http.ui_href("/jeeves", http.BUTLER_HREF) == "/jeeves/assets/jeeves-butler.ico"
    assert http.ui_href("/jeeves", http.LOGO_HREF) == "/jeeves/assets/ntsa-gut-logo.png"


def test_fr7411_login_img_src_uses_prefix():
    html = http._render_login_html(prefix="/jeeves")
    assert 'src="/jeeves/assets/jeeves-butler.ico"' in html
    lan = http._render_login_html()
    assert 'src="/assets/jeeves-butler.ico"' in lan


def test_fr7411_butler_ico_path_pack_layout(tmp_path: Path, monkeypatch):
    pack = tmp_path / "install"
    (pack / "assets").mkdir(parents=True)
    dest = pack / "assets" / "jeeves-butler.ico"
    dest.write_bytes(ICO.read_bytes() if ICO.is_file() else b"\x00\x00\x01\x00")
    monkeypatch.setattr(http, "_REPO_ROOT", pack)
    got = http.butler_ico_path()
    assert got.is_file()
    assert got == dest


def test_fr7411_public_routes_include_butler():
    routes = http.public_jeeves_routes()
    assert "/jeeves/assets/jeeves-butler.ico" in routes
    assert "/jeeves/assets/ntsa-gut-logo.png" in routes


def test_fr7411_bobcallback_serves_prefixed_butler(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    code, body = bobcallback.handle_request(
        "GET",
        "/jeeves/assets/jeeves-butler.ico",
        {},
        b"",
        "8.8.8.8",
        home,
        set(),
    )
    assert code == 200
    assert len(body) > 10


def test_fr7411_bobcallback_serves_pack_layout_butler(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    pack = tmp_path / "pack"
    (pack / "assets").mkdir(parents=True)
    dest = pack / "assets" / "jeeves-butler.ico"
    dest.write_bytes(b"\x00\x00\x01\x00FAKEICO")
    monkeypatch.setattr(http, "_REPO_ROOT", pack)
    code, body = bobcallback.handle_request(
        "GET",
        "/jeeves/assets/jeeves-butler.ico",
        {},
        b"",
        "8.8.8.8",
        home,
        set(),
    )
    assert code == 200
    assert body == dest.read_bytes()


def test_fr7411_script_pins_iis_static_assets():
    text = SCRIPT.read_text(encoding="ascii")
    assert 'fileExtension=".ico" allowed="true"' in text
    assert r'jeeves\assets' in text or "jeeves/assets" in text
    assert "jeeves/assets/" in text
    assert "negate=" in text and "assets" in text


@NEED_PS
def test_fr7411_install_copies_assets_and_excludes_rewrite(tmp_path: Path):
    site = tmp_path / "irc-ntsa"
    site.mkdir()
    args = [
        PS,
        "-NoProfile",
        "-File",
        str(SCRIPT),
        "-PhysicalPath",
        str(site),
        "-Backend",
        "http://127.0.0.1:7700",
        "-PublishWww",
    ]
    r = __import__("subprocess").run(
        args, capture_output=True, text=True, timeout=120, check=False
    )
    assert r.returncode == 0, r.stdout + r.stderr
    ico = site / "jeeves" / "assets" / "jeeves-butler.ico"
    assert ico.is_file(), "IIS static map must copy butler ico"
    cfg = (site / "web.config").read_text(encoding="utf-8")
    assert "jeeves/assets/" in cfg
    assert 'fileExtension=".ico"' in cfg
    assert "negate=" in cfg
