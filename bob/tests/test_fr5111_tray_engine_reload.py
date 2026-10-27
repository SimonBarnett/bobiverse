"""FR #5111: tray-engine-only reload without elevation or ircBob restart."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import ROOT

WIN = sys.platform == "win32"
PS = shutil.which("powershell.exe") or shutil.which("powershell")

CS = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
HELPER = ROOT / "bob" / "tray" / "tools" / "BobTrayDialogs.ps1"
WATCH = ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
FLEET = ROOT / "bob" / "tray" / "tools" / "Start-BobFleetTray.ps1"
DOCS = ROOT / "bob" / "docs" / "bob-tray-dialogs.md"


def test_fr5111_cs_host_reloads_engine_only():
    t = CS.read_text(encoding="utf-8-sig")
    assert "FR #5111" in t
    assert "TakeReload" in t or 'cmd == "reload"' in t or '== "reload"' in t
    assert "--consume-reload" in t
    reload_fn = t[t.find("void ReloadEngine()") : t.find("void ReloadEngine()") + 800]
    assert "KillEngineTree" in reload_fn
    assert "StartEngine" in reload_fn
    assert "sc.exe" not in reload_fn
    assert "Command(" not in reload_fn
    assert "exiting = true" not in reload_fn


def test_fr5111_engine_leaves_reload_for_host():
    h = HELPER.read_text(encoding="utf-8-sig")
    assert "reload" in h.lower()
    assert "FR #5111" in h


def test_fr5111_tipform_restart_skips_ircbob():
    w = WATCH.read_text(encoding="utf-8")
    i = w.index("function Restart-BobTrayWatcher")
    chunk = w[i : i + 2000]
    assert "SkipServiceRestart" in chunk
    f = FLEET.read_text(encoding="utf-8")
    assert "SkipServiceRestart" in f


def test_fr5111_hotpatch_runbook():
    d = DOCS.read_text(encoding="utf-8")
    assert "hot-patch the tray" in d.lower() or "hot-patch" in d.lower()
    assert "reload" in d.lower()
    assert "tray-cmd.txt" in d


@pytest.mark.skipif(not (WIN and PS), reason="needs powershell")
def test_fr5111_engine_pump_leaves_reload_line(tmp_path: Path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "tray-cmd.txt").write_text("ack\nreload\n", encoding="ascii")
    script = (
        ". '{h}'\n"
        "$r = Invoke-BobTrayExeCommands -Root '{root}' -OnAck {{ }} -OnExit {{ }} "
        "-OnRestart {{ }} -ParentGone {{ }}\n"
        "Write-Output ($r -join ',')\n"
        "Write-Output (Get-Content -LiteralPath '{cmd}' -Raw)\n"
    ).format(h=HELPER, root=tmp_path, cmd=run / "tray-cmd.txt")
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "reload" in r.stdout.lower()
