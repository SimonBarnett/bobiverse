"""FR #3318: Plan-seat harvests route to skills-visionary / product, not bobiverse harvest."""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import gitclaim
import intake

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "common" / "scripts" / "Report-BobiverseIntakeIssue.ps1"
HARVEST = ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"
PLAN_AGENTS = ROOT / "bob" / "agents" / "plan" / "AGENTS.md"
VISIONARY = ROOT / "bob" / "agents" / "plan" / ".grok" / "skills" / "visionary" / "SKILL.md"
HSV = (
    ROOT
    / "bob"
    / "agents"
    / "plan"
    / ".grok"
    / "skills"
    / "harvest-skills-visionary"
    / "SKILL.md"
)


def test_fr3318_resolve_skills_visionary_never_bobiverse_harvest_path():
    book, path = intake.resolve_skill_book(
        repo="SimonBarnett/skills-visionary",
        skill_book="harvest",
        title="lesson(harvest): Plan xlsx",
        body="Lessons:\n- Plan seat xlsx helpers\n",
    )
    assert book == "harvest-skills-visionary"
    assert path == ".grok/skills/harvest-skills-visionary/SKILL.md"
    assert path.replace("\\", "/") != "common/.grok/skills/harvest/SKILL.md"
    assert "common/.grok/skills/harvest" not in path.replace("\\", "/")


def test_fr3318_resolve_agentic_fomprep_product_default():
    book, path = intake.resolve_skill_book(
        repo="SimonBarnett/agentic_fomprep",
        skill_book="harvest",
        title="x",
        body="y",
    )
    assert book == "harvest-agent-skills"
    assert path == ".grok/skills/harvest-agent-skills/SKILL.md"


def test_fr3318_report_offline_skills_visionary_not_harvest_book():
    """Report -Repo skills-visionary offline payload must not hardcode skill_book=harvest."""
    with tempfile.TemporaryDirectory() as td:
        outbox = Path(td)
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(REPORT),
                "-Repo",
                "SimonBarnett/skills-visionary",
                "-Kind",
                "harvest",
                "-Title",
                "harvest: Plan-seat process lesson",
                "-Body",
                "Lessons:\n- Plan process belongs in skills-visionary\n",
                "-OutboxDir",
                str(outbox),
                "-IntakeUrl",
                "https://127.0.0.1:9/bob/v1/intake",  # force offline queue
                "-TimeoutSec",
                "2",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(ROOT),
        )
        # Offline path still writes outbox (may non-zero exit on connect fail).
        files = list(outbox.glob("report-*.json"))
        assert files, (proc.stdout or "") + "\n" + (proc.stderr or "")
        payload = json.loads(files[0].read_text(encoding="utf-8"))
        assert payload["repo"] == "SimonBarnett/skills-visionary"
        book = (payload.get("source") or {}).get("skill_book")
        assert book == "harvest-skills-visionary"
        assert book != "harvest"


def test_fr3318_report_explicit_book_wins():
    with tempfile.TemporaryDirectory() as td:
        outbox = Path(td)
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(REPORT),
                "-Repo",
                "SimonBarnett/bobiverse",
                "-Book",
                "bobiverse-bob-job-mrb",
                "-Kind",
                "skill",
                "-Title",
                "skill: mrb note",
                "-Body",
                "body",
                "-OutboxDir",
                str(outbox),
                "-IntakeUrl",
                "https://127.0.0.1:9/bob/v1/intake",
                "-TimeoutSec",
                "2",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(ROOT),
        )
        files = list(outbox.glob("report-*.json"))
        assert files, (proc.stdout or "") + "\n" + (proc.stderr or "")
        payload = json.loads(files[0].read_text(encoding="utf-8"))
        assert (payload.get("source") or {}).get("skill_book") == "bobiverse-bob-job-mrb"


def test_fr3318_plan_agents_names_skills_visionary_not_bobiverse_harvest():
    text = PLAN_AGENTS.read_text(encoding="utf-8")
    assert "FR #3318" in text
    assert "SimonBarnett/skills-visionary" in text
    assert "harvest-skills-visionary" in text or "skills-visionary" in text
    # Must not instruct Plan seats to file *lessons* at bobiverse harvest.
    cast = text.split("## Rules")[0]
    assert "-Repo SimonBarnett/bobiverse" not in cast or "never" in cast.lower()
    assert "never" in cast.lower() and "bobiverse" in cast.lower()


def test_fr3318_visionary_and_hsv_cast_iron_point_at_skills_visionary():
    for path in (VISIONARY, HSV):
        text = path.read_text(encoding="utf-8")
        assert "SimonBarnett/skills-visionary" in text
        # CAST IRON example line should not default Report to bobiverse.
        head = "\n".join(text.splitlines()[:30])
        assert "Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/skills-visionary" in head


def test_fr3318_product_404_holds_not_bobiverse_harvest_pr(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": "SimonBarnett/iphone-text-bridge",
            "title": "harvest: Shortcuts recipe",
            "body": "Lessons:\n- Shortcuts all-SMS recipe\n",
            "source": {"skill_book": "harvest", "agent": "Report-BobiverseIntakeIssue"},
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_fr3318_hold")
    assert rec["state"] == "held_owner_missing"
    assert filer.prs == []
    assert filer.issues
    issue = filer.issues[-1]
    assert issue["repo"] == "SimonBarnett/bobiverse"
    labs = {str(x).lower() for x in (issue.get("labels") or [])}
    assert intake.OWNER_MISSING_LABEL in labs
    assert (
        gitclaim.issue_skip_fr_reason(
            title=issue["title"],
            body=issue.get("body") or "",
            labels=tuple(issue.get("labels") or ()),
        )
        == f"label:{intake.OWNER_MISSING_LABEL}"
    )


def test_fr3318_harvest_dryrun_skills_visionary_book_path():
    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(HARVEST),
            "-Repo",
            "SimonBarnett/skills-visionary",
            "-Summary",
            "Plan seat xlsx",
            "-Lesson",
            "Plan process lessons belong in skills-visionary",
            "-DryRun",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(ROOT),
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, out
    assert "SimonBarnett/skills-visionary" in out
    assert "harvest-skills-visionary" in out
    assert "common/.grok/skills/harvest/SKILL.md" not in out or (
        "skill_book_path=.grok/skills/harvest-skills-visionary/SKILL.md" in out
        or '"skill_book_path":  ".grok/skills/harvest-skills-visionary/SKILL.md"' in out
    )
