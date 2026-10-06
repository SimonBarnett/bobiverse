"""FR #2699: grok Plan (and every seat mode) must pass --no-auto-update / --no-alt-screen."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import bob_worker as bw
from repo_layout import ROOT


@pytest.mark.parametrize("mode", ["agent", "plan", "monitor", "maintenance"])
def test_grok_build_launch_always_has_no_auto_update_and_no_alt_screen(tmp_path, mode):
    spec = bw.build_launch(
        "grok",
        mode,
        r"C:\ai\bob\worker" if mode != "plan" else r"C:\ai\bob\plan",
        "prompt",
        r"C:\g\agent.exe",
        tmp_path,
        session_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    )
    assert "--no-auto-update" in spec.argv
    assert "--no-alt-screen" in spec.argv
    # Common prefix: exe, both flags, then --cwd (FR #2699).
    assert spec.argv[0] == r"C:\g\agent.exe"
    assert spec.argv[1:4] == ["--no-auto-update", "--no-alt-screen", "--cwd"]
    if mode == "plan":
        assert "--permission-mode" in spec.argv
        assert "plan" in spec.argv
        i = spec.argv.index("--permission-mode")
        assert spec.argv[i + 1] == "plan"


def test_grok_plan_describe_child_includes_no_auto_update(tmp_path):
    cwd = tmp_path / "plan"
    cwd.mkdir()
    (cwd / ".grok" / "skills").mkdir(parents=True)
    run = tmp_path / "run" / "plan-x"
    run.mkdir(parents=True)
    child = bw.describe_agent_child_launch(
        kind="grok",
        mode="plan",
        cwd=str(cwd),
        run_dir=run,
        machine="marchhare",
        nick="marchhare-plan",
        agent_exe=r"C:\g\agent.exe",
    )
    assert "--no-auto-update" in child["argv"]
    assert "--no-alt-screen" in child["argv"]
    assert child["argv"][1:4] == ["--no-auto-update", "--no-alt-screen", "--cwd"]


def test_hostile_build_launch_is_only_grok_seat_argv_builder():
    """Seat grok argv with --no-auto-update / permission-mode must come from build_launch only."""
    src = (ROOT / "bob" / "scripts" / "bob_worker.py").read_text(encoding="utf-8")
    # Exactly one assignment site for the shared prefix (FR #2699).
    assert src.count('prefix = [exe, "--no-auto-update", "--no-alt-screen", "--cwd", cwd]') == 1
    # Plan must not rebuild argv without the prefix.
    plan_branch = re.search(
        r'if mode == "plan":\s*\n\s*argv = (.+)',
        src,
    )
    assert plan_branch, "plan branch missing in build_launch"
    assert "prefix" in plan_branch.group(1)
    assert "--no-auto-update" not in plan_branch.group(1) or "prefix" in plan_branch.group(1)


def test_hostile_tray_and_cs_do_not_build_raw_grok_plan_argv():
    """Tray/C# seat starts go through bob-worker --describe-launch, not a local agent.exe argv."""
    tray = (ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1").read_text(encoding="utf-8")
    cs = (ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs").read_text(encoding="utf-8-sig")
    assert "--describe-launch" in tray and "Start-BobTrayWorkerExe" in tray
    assert "TryDescribeLaunch" in cs and "--describe-launch" in cs
    # Must not hand-roll grok plan permission-mode argv in the tray host.
    assert "--permission-mode" not in tray
    assert "--permission-mode" not in cs
