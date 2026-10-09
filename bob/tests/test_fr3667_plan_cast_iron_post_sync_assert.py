"""FR #3667: after Sync-BobiverseAgentFolders, plan CAST IRON must stay skills-visionary.

#3506 / #3510 already pin tracked bob/agents/plan sources. Stale install trees
(pre-#3510) needed Sync/ff. This FR adds a post-sync assert so Sync/Pack surfaces
a WARN when destination plan\\AGENTS.md still shows the bobiverse CAST IRON example.
Do not re-land #3510 content.
"""
from __future__ import annotations

import re
import subprocess
import sys

import pytest

from repo_layout import ROOT

COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
SYNC_FROM = ROOT / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1"
INSTALL_BOB = ROOT / "bob" / "scripts" / "Install-Bob.ps1"
WIN = pytest.mark.skipif(sys.platform != "win32", reason="PowerShell Sync is Windows-only")


def _read(path) -> str:
    return path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")


def test_fr3667_assert_function_and_call_sites():
    common = _read(COMMON)
    assert "function Assert-BobiversePlanCastIronSkillsVisionary" in common
    assert "FR #3667" in common
    # Soft WARN (do not hard-fail Sync on a stale dest) + the bad-example cue.
    fn = common[
        common.index("function Assert-BobiversePlanCastIronSkillsVisionary") :
        common.index("function Assert-BobiversePlanCastIronSkillsVisionary") + 2200
    ]
    assert "skills-visionary" in fn
    assert "Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse" in fn
    assert "WARN" in fn
    assert "Sync-BobiverseAgentFolders" in common
    # Called from Sync-BobiverseAgentFolders after plan AGENTS is written.
    sync_fn = common[
        common.index("function Sync-BobiverseAgentFolders") :
        common.index("function Install-BobiverseAgentLayer")
    ]
    assert "Assert-BobiversePlanCastIronSkillsVisionary" in sync_fn


def test_fr3667_sync_from_repo_still_calls_agent_folders():
    # Heal path remains Sync-BobiverseFromRepo -> Sync-BobiverseAgentFolders (issue Fix).
    text = _read(SYNC_FROM)
    assert "Sync-BobiverseAgentFolders" in text
    assert "Product -eq 'bob'" in text or "$Product -eq 'bob'" in text
    # Install-Bob also refreshes agent folders.
    assert "Sync-BobiverseAgentFolders" in _read(INSTALL_BOB)


def test_fr3667_tracked_plan_agents_already_skills_visionary():
    # Do not re-implement #3510: sources on tip must already be correct.
    agents = _read(ROOT / "bob" / "agents" / "plan" / "AGENTS.md")
    start = agents.index("CAST IRON RULE - HARVEST")
    block = agents[start : start + 2500]
    assert "Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/skills-visionary" in block
    assert "Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse" not in block
    assert "Sync/ff" in agents or "stale install" in agents.lower()


def test_fr3667_heal_notes_in_bob_plan_and_fleet_ops():
    plan = _read(ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-plan" / "SKILL.md")
    assert "FR #3667" in plan
    assert "Sync-BobiverseFromRepo" in plan or "Sync-BobiverseAgentFolders" in plan
    assert "Do not re-land #3510" in plan or "Do not re-land #3510 source" in plan
    fleet = _read(ROOT / "common" / ".grok" / "skills" / "bobiverse-fleet-ops" / "SKILL.md")
    assert "FR #3667" in fleet or "class of #3667" in fleet
    assert "skills-visionary" in fleet or "WARN FR #3667" in fleet


@WIN
def test_fr3667_sync_dest_plan_agents_pass_assert(tmp_path):
    dest = tmp_path / "inst"
    dest.mkdir()
    # Seed a deliberately stale plan AGENTS so Sync must overwrite it.
    stale = dest / "plan"
    stale.mkdir()
    (stale / "AGENTS.md").write_text(
        "# stale\n> CAST IRON\n"
        "`..\\scripts\\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind harvest`\n",
        encoding="utf-8",
    )
    ps = tmp_path / "s.ps1"
    ps.write_text(
        ". '%s'\n"
        "$n = Sync-BobiverseAgentFolders -RepoRoot '%s' -Destination '%s'\n"
        "Write-Output \"MADE=$n\"\n"
        "Assert-BobiversePlanCastIronSkillsVisionary -InstallRoot '%s'\n"
        "Write-Output 'ASSERT_OK'\n"
        % (COMMON, ROOT, dest, dest),
        encoding="utf-8",
    )
    r = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ps),
        ],
        capture_output=True,
        text=True,
        timeout=180,
        creationflags=0x08000000,
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out[-800:]
    assert "MADE=2" in out, out[-800:]
    assert "ASSERT_OK" in out, out[-800:]
    assert "INFO FR #3667 plan CAST IRON skills-visionary ok" in out, out[-800:]
    # Soft assert must not WARN after a successful Sync from tip sources.
    assert "WARN FR #3667" not in out, out[-800:]
    agents = (dest / "plan" / "AGENTS.md").read_text(encoding="utf-8")
    assert "Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/skills-visionary" in agents
    assert not re.search(
        r"Report-BobiverseIntakeIssue\.ps1 -Repo SimonBarnett/bobiverse",
        agents[:2500],
    )


@WIN
def test_fr3667_assert_warns_on_stale_plan_agents(tmp_path):
    root = tmp_path / "bad-inst"
    plan = root / "plan"
    plan.mkdir(parents=True)
    (plan / "AGENTS.md").write_text(
        "# AGENTS\n"
        "> **CAST IRON RULE - HARVEST AND FILE EVERYTHING**\n"
        "> Example:\n"
        "> `..\\scripts\\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind harvest -Title t -Body b`\n"
        "> `..\\scripts\\Invoke-BobiverseHarvest.ps1 -Repo SimonBarnett/bobiverse -Summary s -Lesson l`\n",
        encoding="utf-8",
    )
    ps = tmp_path / "a.ps1"
    ps.write_text(
        ". '%s'\n"
        "Assert-BobiversePlanCastIronSkillsVisionary -InstallRoot '%s'\n"
        "Write-Output 'DONE'\n"
        % (COMMON, root),
        encoding="utf-8",
    )
    r = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ps),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        creationflags=0x08000000,
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out[-600:]
    assert "DONE" in out
    assert "WARN FR #3667" in out
    assert "skills-visionary" in out
