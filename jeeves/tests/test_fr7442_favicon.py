"""FR #7442: bob.ntsa.uk favicon is the Bob tray icon (bob-systray.ico)."""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path

from repo_layout import REPO

TRAY_ICO = REPO / "bob" / "tray" / "assets" / "bob-systray.ico"
WWW_ICO = REPO / "jeeves" / "www" / "favicon.ico"
WWW_ROOT = REPO / "jeeves" / "www"
WWW_PUBLISH = REPO / "jeeves" / "www" / "irc-ntsa"
INSTALL = REPO / "jeeves" / "scripts" / "Install-BobWebhooks.ps1"
DOCS = REPO / "jeeves" / "docs" / "webhooks.md"

PS = shutil.which("powershell.exe") or shutil.which("pwsh")
NEED_PS = __import__("pytest").mark.skipif(not PS, reason="PowerShell required")

ICON_HREF = re.compile(r"""rel=["']icon["'][^>]*href=["']/favicon\.ico["']|href=["']/favicon\.ico["'][^>]*rel=["']icon["']""", re.I)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_fr7442_www_favicon_byte_identical_to_tray_icon():
    assert TRAY_ICO.is_file(), "tray source icon missing"
    assert WWW_ICO.is_file(), "jeeves/www/favicon.ico must be checked in"
    assert _sha256(WWW_ICO) == _sha256(TRAY_ICO)


def test_fr7442_every_www_html_has_icon_link():
    pages = sorted(WWW_ROOT.rglob("*.html"))
    assert pages, "expected HTML under jeeves/www"
    missing = []
    for page in pages:
        text = page.read_text(encoding="utf-8")
        if not ICON_HREF.search(text) and 'href="/favicon.ico"' not in text:
            missing.append(str(page.relative_to(REPO)))
        elif 'rel="icon"' not in text and "rel='icon'" not in text:
            missing.append(str(page.relative_to(REPO)))
    assert not missing, "pages missing favicon link: " + ", ".join(missing)


def test_fr7442_install_script_pins_favicon_publish_and_mime():
    text = INSTALL.read_text(encoding="utf-8-sig")
    assert "favicon.ico" in text
    assert "7442" in text
    assert "image/x-icon" in text
    assert "bob-systray.ico" in text or "www\\favicon.ico" in text or "www/favicon.ico" in text


def test_fr7442_docs_note_favicon():
    text = DOCS.read_text(encoding="utf-8")
    assert "7442" in text
    assert "favicon" in text.lower()
    assert "image/x-icon" in text


@NEED_PS
def test_fr7442_install_publishes_favicon_and_mime(tmp_path: Path):
    www = tmp_path / "www-src"
    shutil.copytree(WWW_PUBLISH, www)
    # Parent favicon beside irc-ntsa-style tree (Install looks at ..\favicon.ico).
    shutil.copy2(WWW_ICO, www.parent / "favicon.ico")
    site = tmp_path / "iis-physical"
    site.mkdir()
    args = [
        PS,
        "-NoProfile",
        "-File",
        str(INSTALL),
        "-PhysicalPath",
        str(site),
        "-Backend",
        "http://127.0.0.1:7700",
        "-WwwSource",
        str(www),
    ]
    r = subprocess.run(args, capture_output=True, text=True, timeout=120, check=False)
    assert r.returncode == 0, r.stdout + "\n" + r.stderr
    published = site / "favicon.ico"
    assert published.is_file(), "publish must include favicon.ico"
    assert _sha256(published) == _sha256(TRAY_ICO)
    cfg = (site / "web.config").read_text(encoding="utf-8")
    assert "image/x-icon" in cfg
    assert 'fileExtension=".ico"' in cfg or "fileExtension=\".ico\"" in cfg
