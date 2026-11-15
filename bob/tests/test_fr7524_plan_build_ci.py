"""FR #7524: isolated build-bob-plan CI for the Plan agent (FR #7276 per-component)."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

WF = ROOT / ".github" / "workflows" / "build-bob-plan.yml"
PLAN = ROOT / "bob" / "agents" / "plan"
PLAN_SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-plan" / "SKILL.md"
WORKFLOWS = ROOT / ".github" / "workflows"


def _wf() -> str:
    return WF.read_text(encoding="utf-8")


def test_fr7524_plan_ci_workflow_pins():
    assert WF.is_file(), "missing .github/workflows/build-bob-plan.yml"
    text = _wf()
    assert "name: build-bob-plan" in text
    assert "runs-on: windows-latest" in text
    assert "workflow_dispatch" in text
    assert "bob/agents/plan/**" in text
    assert "bob/.grok/skills/bobiverse-bob-plan/**" in text
    assert "bob/tests/test_fr7524_plan_build_ci.py" in text
    assert "persist-credentials: false" in text
    assert "upload-artifact@v4" in text
    assert "name: bob-plan" in text
    assert "MANIFEST.json" in text or "manifest.json" in text
    assert "Get-FileHash -Algorithm SHA256" in text
    assert "source_commit" in text
    assert "PSScriptAnalyzer" in text or "Invoke-ScriptAnalyzer" in text
    assert "bob/agents/plan/tests" in text
    assert "pytest" in text
    assert "SKILL.md" in text
    assert PLAN.is_dir()
    assert PLAN_SKILL.is_file()
    assert (PLAN / "AGENTS.md").is_file()
    assert (PLAN / "tools").is_dir()
    assert (PLAN / "tests").is_dir()


def test_fr7524_other_component_workflows_do_not_own_plan():
    """Exactly one CI owner for plan paths (FR #7276 / #7524)."""
    owners = []
    # Use iterdir: pathlib glob('*.yml') can return empty on some Windows worktree paths.
    for path in sorted(WORKFLOWS.iterdir()):
        if path.suffix.lower() != ".yml":
            continue
        text = path.read_text(encoding="utf-8")
        if "bob/agents/plan" in text or "bobiverse-bob-plan" in text:
            owners.append(path.name)
    assert owners == ["build-bob-plan.yml"], owners


def test_fr7524_plan_skill_front_matter():
    raw = PLAN_SKILL.read_text(encoding="utf-8-sig")
    assert raw.lstrip().startswith("---"), "bobiverse-bob-plan SKILL.md needs YAML front matter"
    for skill in (PLAN / ".grok" / "skills").glob("*/SKILL.md"):
        body = skill.read_text(encoding="utf-8-sig")
        assert body.lstrip().startswith("---"), f"{skill} missing front matter"
