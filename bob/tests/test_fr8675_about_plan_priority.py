"""FR #8675 / BOB-10: About shows non-empty Plan and Priority version fields."""
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
ABOUT = REPO / "bob" / "tray" / "dialogs" / "BobAbout.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"


def test_about_sources_name_plan_and_priority_versions():
    about = ABOUT.read_text(encoding="utf-8-sig")
    watch = WATCH.read_text(encoding="utf-8-sig")
    assert 'agents.Name = "agentBuildVersions"' in about
    assert 'Common.SliceVersion(root, "plan")' in about
    assert 'Common.SliceVersion(root, "priority")' in about
    assert "Plan version:" in about and "Priority version:" in about
    assert "agentBuildVersions" in watch
    assert "Get-BobTraySliceVersion -Slice 'plan'" in watch
    assert "Get-BobTraySliceVersion -Slice 'priority'" in watch


@pytest.mark.skipif(not (WIN and CSC.is_file()), reason="needs Windows csc")
def test_about_text_out_plan_and_priority_nonempty(tmp_path: Path):
    out_dir = tmp_path / "dlg"
    out_dir.mkdir()
    src = REPO / "bob" / "tray" / "dialogs"
    exe = out_dir / "bob-about.exe"
    argv = [
        str(CSC), "/nologo", "/target:winexe", "/optimize+", "/platform:anycpu",
        f"/out:{exe}",
        "/r:System.dll", "/r:System.Core.dll", "/r:System.Drawing.dll",
        "/r:System.Windows.Forms.dll", "/r:System.Web.Extensions.dll",
        "/r:System.ServiceProcess.dll",
        "/main:BobDialogs.AboutProgram",
        str(src / "BobDialogsCommon.cs"),
        str(src / "CrashHook.cs"),
        str(src / "BobAbout.cs"),
    ]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    ai = tmp_path / "ai"
    bob = ai / "bob"
    (bob / "scripts").mkdir(parents=True)
    (bob / "VERSION").write_text("9.8.7\n", encoding="utf-8")
    (bob / "plan").mkdir()
    (bob / "plan" / "VERSION").write_text("1.2.3-plan\n", encoding="utf-8")
    (bob / "priority").mkdir()
    (bob / "priority" / "VERSION").write_text("4.5.6-priority\n", encoding="utf-8")
    text_out = tmp_path / "about.txt"
    env = dict(os.environ)
    env["BOB_AI_ROOT"] = str(ai)
    p = subprocess.Popen(
        [str(out_dir / "bob-about.exe"), "--root", str(bob), "--text-out", str(text_out)],
        env=env,
    )
    assert p.wait(timeout=60) == 0
    text = text_out.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert "Plan version: 1.2.3-plan" in text
    assert "Priority version: 4.5.6-priority" in text
    assert "bob  9.8.7" in text
