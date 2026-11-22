"""FR #8717 / BOB-24: Workers > Cursor uses the cursor.com favicon."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import REPO

WIN = sys.platform == "win32"
CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
PS = shutil.which("powershell.exe") or shutil.which("powershell") or shutil.which("pwsh")
TRAY = REPO / "bob" / "tray"
ICO = TRAY / "assets" / "menu-favicons" / "cursor.com.ico"
CS = TRAY / "dialogs" / "BobTray.cs"
WATCH = TRAY / "tools" / "Watch-BobTray.ps1"
BUILD = REPO / "bob" / "scripts" / "Build-BobDialogs.ps1"


def test_fr8717_favicon_asset_and_menu_pins():
    raw = ICO.read_bytes()
    assert raw[:4] == b"\x00\x00\x01\x00"
    cs = CS.read_text(encoding="utf-8-sig")
    assert "cursor.com.ico" in cs
    assert "worker-favicon" in cs
    assert "ApplyWorkerFavicon" in cs
    watch = WATCH.read_text(encoding="utf-8-sig")
    assert "cursor.com.ico" in watch
    assert "worker-favicon id=cursor" in watch


@pytest.mark.skipif(not (WIN and CSC.is_file() and PS), reason="needs Windows csc and powershell")
def test_fr8717_dump_worker_favicon_path(tmp_path: Path):
    out_dir = tmp_path / "dlg"
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(BUILD), "-RepoRoot", str(REPO), "-OutDir", str(out_dir)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    exe = out_dir / "bob-tray.exe"
    dump = tmp_path / "fav.txt"
    p = subprocess.run(
        [str(exe), "--root", str(TRAY), "--dump-worker-favicon", str(dump), "--no-engine"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    text = dump.read_text(encoding="utf-8").strip()
    assert text.replace("/", "\\").lower().endswith("menu-favicons\\cursor.com.ico")
    assert Path(text).is_file()
    assert Path(text).read_bytes()[:4] == b"\x00\x00\x01\x00"
