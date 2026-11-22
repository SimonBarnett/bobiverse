"""FR #8675 / BOB-10: About shows non-empty Plan and Priority build versions."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import REPO, ROOT

WIN = sys.platform == "win32"
CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
PS = shutil.which("powershell.exe") or shutil.which("powershell") or shutil.which("pwsh")
ABOUT = REPO / "bob" / "tray" / "dialogs" / "BobAbout.cs"
COMMON = REPO / "bob" / "tray" / "dialogs" / "BobDialogsCommon.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
INFO = REPO / "bob" / "tray" / "tools" / "Get-BobInstallInfo.ps1"
BOB_COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"


def test_fr8675_sources_pin_plan_priority_and_versions_out():
    about = ABOUT.read_text(encoding="utf-8-sig")
    common = COMMON.read_text(encoding="utf-8-sig")
    watch = WATCH.read_text(encoding="utf-8-sig")
    info = INFO.read_text(encoding="utf-8-sig")
    assert "PlanVersion" in common and "PriorityVersion" in common
    assert "SliceVersion" not in common
    assert "priority-agent" in common and "priority-mcp" in common
    assert "(via bob)" in common
    assert "not installed" in common
    assert "PlanVersion(root)" in about and "PriorityVersion(root)" in about
    assert "--versions-out" in about
    # --text-out inventory contract unchanged (no Plan version: head)
    assert "Plan version:" not in about
    assert "Get-BobTrayPlanVersion" in watch
    assert "Get-BobTrayPriorityVersion" in watch
    assert "Get-BobTraySliceVersion" not in watch
    assert "function Get-BobComponentVersions" in info
    assert "Write-BobiversePlanIdentity" in BOB_COMMON.read_text(encoding="utf-8-sig")
    assert "Write-BobiversePlanIdentity" in PACK.read_text(encoding="utf-8-sig")


def test_fr8675_plan_identity_helper_behaviour(tmp_path: Path):
    if not PS:
        pytest.skip("powershell required")
    dest = tmp_path / "bob"
    (dest / "plan").mkdir(parents=True)
    script = f"""
. '{BOB_COMMON}'
Write-BobiversePlanIdentity -Destination '{dest}' -Version '1.2.3' -Commit 'abcdef1'
Get-Content -LiteralPath '{dest / "plan" / "VERSION"}' -TotalCount 1
(Get-Content -LiteralPath '{dest / "plan" / "BUILD.json"}' -Raw | ConvertFrom-Json).commit
"""
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert (dest / "plan" / "VERSION").read_text(encoding="utf-8").splitlines()[0].strip() == "1.2.3"
    assert "abcdef1" in (dest / "plan" / "BUILD.json").read_text(encoding="utf-8")
    # empty version skips stamp
    dest2 = tmp_path / "bob2"
    (dest2 / "plan").mkdir(parents=True)
    script2 = f"""
. '{BOB_COMMON}'
Write-BobiversePlanIdentity -Destination '{dest2}' -Version '' -Commit 'abcdef1'
if (Test-Path -LiteralPath '{dest2 / "plan" / "VERSION"}') {{ 'HAS' }} else {{ 'NONE' }}
"""
    r2 = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script2],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert "NONE" in r2.stdout


@pytest.mark.skipif(not (WIN and CSC.is_file() and PS), reason="needs Windows csc and powershell")
def test_fr8675_versions_out_stamped_and_fallbacks(tmp_path: Path):
    out_dir = tmp_path / "dlg"
    r = subprocess.run(
        [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(REPO / "bob" / "scripts" / "Build-BobDialogs.ps1"),
            "-RepoRoot",
            str(REPO),
            "-OutDir",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    about_exe = out_dir / "bob-about.exe"
    assert about_exe.is_file()

    ai = tmp_path / "ai"
    bob = ai / "bob"
    (bob / "scripts").mkdir(parents=True)
    (bob / "VERSION").write_text("9.8.7\n", encoding="utf-8")
    (bob / "plan").mkdir()
    (bob / "plan" / "VERSION").write_text("1.2.3-plan\n", encoding="utf-8")
    (bob / "plan" / "BUILD.json").write_text(
        '{"product":"plan","version":"1.2.3-plan","commit":"abcdef1234567","built_utc":"2026-01-01T00:00:00Z"}\n',
        encoding="utf-8",
    )
    pa = ai / "priority-agent"
    pa.mkdir()
    (pa / "VERSION").write_text("4.5.6-priority\n", encoding="utf-8")

    versions_out = tmp_path / "versions.txt"
    env = dict(os.environ)
    env["BOB_AI_ROOT"] = str(ai)
    p = subprocess.run(
        [str(about_exe), "--root", str(bob), "--versions-out", str(versions_out)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    raw = versions_out.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in raw
    text = raw.decode("utf-8")
    assert "plan 1.2.3-plan (abcdef1)" in text
    assert "priority 4.5.6-priority" in text
    assert "bob 9.8.7" in text or "bob  9.8.7" in text

    # Fallback fixture: no plan stamp, no priority folder
    bob2 = tmp_path / "bob2"
    (bob2 / "scripts").mkdir(parents=True)
    (bob2 / "VERSION").write_text("0.1.0\n", encoding="utf-8")
    versions2 = tmp_path / "versions2.txt"
    env2 = dict(os.environ)
    env2["BOB_AI_ROOT"] = str(tmp_path / "empty-ai")
    (tmp_path / "empty-ai").mkdir(exist_ok=True)
    p2 = subprocess.run(
        [str(about_exe), "--root", str(bob2), "--versions-out", str(versions2)],
        env=env2,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert p2.returncode == 0, p2.stdout + p2.stderr
    t2 = versions2.read_text(encoding="utf-8")
    assert "(via bob)" in t2
    assert "not installed" in t2

    # --text-out must not grow Plan version: header
    text_out = tmp_path / "text.txt"
    p3 = subprocess.run(
        [str(about_exe), "--root", str(bob), "--text-out", str(text_out)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert p3.returncode == 0, p3.stdout + p3.stderr
    assert "Plan version:" not in text_out.read_text(encoding="utf-8")
