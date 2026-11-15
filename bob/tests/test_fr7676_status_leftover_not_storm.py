"""FR #7676: leftover tray-status.json must not kill a heartbeating engine."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from repo_layout import ROOT

WIN = pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell"), reason="needs Windows PowerShell")
CS = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
BUILD = ROOT / "bob" / "scripts" / "Build-BobDialogs.ps1"
PS = shutil.which("powershell") or "powershell.exe"


def test_fr7676_status_age_ignores_pre_start_file():
    t = CS.read_text(encoding="utf-8-sig")
    body = t[t.find("internal static class TrayStatusAge") : t.find("internal static class TrayStatusAge") + 1200]
    assert "written < engineStartedUtc" in body
    assert "FR #7676" in body
    assert "--status-age-eval" in t


@WIN
def test_fr7676_leftover_status_not_stale_at_15s(tmp_path):
    out_dir = tmp_path / "dialogs"
    out_dir.mkdir()
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(BUILD), "-RepoRoot", str(ROOT), "-OutDir", str(out_dir)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    exe = out_dir / "bob-tray.exe"
    root = tmp_path / "root"
    (root / "run").mkdir(parents=True)
    snap = root / "run" / "tray-status.json"
    snap.write_text("{}", encoding="ascii")
    old = time.time() - 3600
    os.utime(snap, (old, old))
    text_out = tmp_path / "age15.txt"
    p = subprocess.run(
        [str(exe), "--root", str(root), "--status-age-eval", "--engine-started-ago-s", "15", "--text-out", str(text_out)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    body = text_out.read_text(encoding="utf-8")
    assert "statusStale=0" in body, body
    assert p.returncode == 0
    text_out2 = tmp_path / "age200.txt"
    p2 = subprocess.run(
        [str(exe), "--root", str(root), "--status-age-eval", "--engine-started-ago-s", "200", "--text-out", str(text_out2)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    body2 = text_out2.read_text(encoding="utf-8")
    assert "statusStale=1" in body2, body2
    assert p2.returncode == 2


def test_fr7676_mrb_fresh_status_age_path_and_heal_wiring():
    """Hostile: post-start mtime path + HealEngine still consults TrayStatusAge."""
    t = CS.read_text(encoding="utf-8-sig")
    assert "DateTime written = File.GetLastWriteTimeUtc(snapFile);" in t
    assert "double age = (DateTime.UtcNow - written).TotalSeconds;" in t
    assert "bool statusStale = TrayStatusAge.IsStale(snapFile, engineStartedUtc" in t
    body = t[t.find("internal static class TrayStatusAge") : t.find("internal static class TrayStatusAge") + 1600]
    assert body.index("written < engineStartedUtc") < body.index("double age =")

