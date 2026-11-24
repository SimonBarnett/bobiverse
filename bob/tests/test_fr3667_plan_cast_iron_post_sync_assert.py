"""FR #3667: Assert-BobiversePlanCastIronSkillsVisionary soft-WARN on stale plan\\AGENTS.

FR #8833: Sync no longer refreshes plan\\ from bob/agents/plan. Pack writes the
skills-visionary stub AGENTS at stage time. Assert still soft-checks when the
file exists (install trees / MSI stage).
"""
from __future__ import annotations

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
    fn = common[
        common.index("function Assert-BobiversePlanCastIronSkillsVisionary") :
        common.index("function Assert-BobiversePlanCastIronSkillsVisionary") + 2200
    ]
    assert "skills-visionary" in fn
    assert "Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse" in fn
    assert "WARN" in fn
    assert "Sync-BobiverseAgentFolders" in common
    sync_fn = common[
        common.index("function Sync-BobiverseAgentFolders") :
        common.index("function Write-BobiversePlanIdentity")
    ]
    assert "Assert-BobiversePlanCastIronSkillsVisionary" in sync_fn


def test_fr3667_sync_from_repo_still_calls_agent_folders():
    text = _read(SYNC_FROM)
    assert "Sync-BobiverseAgentFolders" in text
    assert "Product -eq 'bob'" in text or "$Product -eq 'bob'" in text
    assert "Sync-BobiverseAgentFolders" in _read(INSTALL_BOB)


def test_fr3667_pack_stub_is_skills_visionary():
    pack = _read(ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1")
    assert "Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/skills-visionary" in pack
    assert "FR #8833" in pack


def test_fr3667_heal_notes_in_fleet_ops():
    fleet = _read(ROOT / "common" / ".grok" / "skills" / "bobiverse-fleet-ops" / "SKILL.md")
    assert "FR #3667" in fleet or "class of #3667" in fleet
    assert "skills-visionary" in fleet or "WARN FR #3667" in fleet


@WIN
def test_fr3667_sync_worker_only_made_one(tmp_path):
    dest = tmp_path / "inst"
    dest.mkdir()
    (dest / "plan" / "work" / "keep").mkdir(parents=True)
    (dest / "plan" / "work" / "keep" / "vision.md").write_text("my plan", encoding="utf-8")
    ps = tmp_path / "s.ps1"
    ps.write_text(
        ". '%s'\n"
        "$n = Sync-BobiverseAgentFolders -RepoRoot '%s' -Destination '%s'\n"
        "Write-Output \"MADE=$n\"\n"
        % (COMMON, ROOT, dest),
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
    assert "MADE=1" in out, out[-800:]
    assert (dest / "plan" / "work" / "keep" / "vision.md").read_text(encoding="utf-8") == "my plan"
    assert (dest / "worker" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md").is_file()


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
