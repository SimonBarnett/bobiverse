"""FR #8833: Plan source removed; pointer README + pack vendors PlanAgent.exe."""
from __future__ import annotations

import re

from repo_layout import ROOT

README = ROOT / "bob" / "agents" / "plan" / "README.md"
PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"


def test_fr8833_readme_points_at_skills_visionary():
    assert README.is_file()
    text = README.read_text(encoding="utf-8")
    assert "https://github.com/SimonBarnett/skills-visionary" in text
    assert "releases/latest" in text
    assert "8833" in text or "FR #8833" in text


def test_fr8833_no_in_tree_plan_agents_or_skill_book():
    assert not (ROOT / "bob" / "agents" / "plan" / "AGENTS.md").exists()
    assert not (ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-plan").exists()
    assert not (ROOT / ".github" / "workflows" / "build-bob-plan.yml").exists()
    assert not (ROOT / "bob" / "tests" / "test_fr7524_plan_build_ci.py").exists()


def test_fr8833_pack_requires_worker_only_and_vendors_plan():
    text = PACK.read_text(encoding="utf-8-sig")
    assert "bob pack requires bob-agents\\worker" in text
    assert "bob pack requires bob-agents\\worker and bob-agents\\plan" not in text
    assert "PlanAgent.exe" in text
    assert "SimonBarnett/skills-visionary" in text
    assert "FR #8833" in text


def test_fr8833_sync_agent_folders_worker_only():
    common = COMMON.read_text(encoding="utf-8-sig")
    sync = common[
        common.index("function Sync-BobiverseAgentFolders") : common.index(
            "function Write-BobiversePlanIdentity"
        )
    ]
    assert "Name = 'worker'" in sync
    assert "Name = 'plan'" not in sync
    # Shared list must not require the deleted book (comment may still name it).
    assert "bobiverse-bob-plan'" not in sync
    assert "'bobiverse-bob-plan'" not in sync


def test_fr8833_git_grep_plan_path_is_readme_or_history():
    """Acceptance: bob/agents/plan hits are README (and changelog/history notes)."""
    from pathlib import Path

    plan_dir = Path(ROOT) / "bob" / "agents" / "plan"
    files = sorted(
        p.relative_to(Path(ROOT)).as_posix() for p in plan_dir.iterdir() if p.is_file()
    )
    assert files == ["bob/agents/plan/README.md"]


def test_fr8833_intake_does_not_map_bobiverse_bob_plan():
    import intake

    assert "bobiverse-bob-plan" not in intake.SKILL_BOOK_PATHS
    book, path = intake.resolve_skill_book(
        repo="SimonBarnett/bobiverse",
        skill_book="harvest",
        title="plan vision lesson",
        body="Lessons:\n- plan vision CAST IRON\n",
    )
    assert book != "bobiverse-bob-plan"
    assert "bobiverse-bob-plan" not in (path or "")
