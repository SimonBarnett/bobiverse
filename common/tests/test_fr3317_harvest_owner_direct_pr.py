"""FR #3317: harvest PRs open in the owning skill book; light MRB triage; hold missing owners."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import gitclaim
import intake
import re


REPO_ROOT = Path(__file__).resolve().parents[2]
HARVEST_PS1 = REPO_ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"
JOB_MRB = (
    REPO_ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
)


def _dry_run(*, job_repo: str, summary: str, lesson: str) -> str:
    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-File",
            str(HARVEST_PS1),
            "-JobRepo",
            job_repo,
            "-Summary",
            summary,
            "-Lesson",
            lesson,
            "-DryRun",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, out
    return out


def test_fr3317_dryrun_a_search_emits_repo_and_skill_path():
    out = _dry_run(
        job_repo="SimonBarnett/a-search",
        summary="a-search Madeira shopify stub",
        lesson="scaffold disabled local stubs",
    )
    assert "repo=SimonBarnett/a-search" in out or '"repo":  "SimonBarnett/a-search"' in out
    assert "skill_book_path=.grok/skills/harvest-agent-skills/SKILL.md" in out or (
        '"skill_book_path":  ".grok/skills/harvest-agent-skills/SKILL.md"' in out
    )
    assert "harvest-agent-skills" in out


def test_fr3317_dryrun_bob_worker_tooling_stays_bobiverse():
    out = _dry_run(
        job_repo="SimonBarnett/a-search",
        summary="bob-worker done-miss _release_gen",
        lesson="_release_gen must bump when DONE is drained",
    )
    assert "SimonBarnett/bobiverse" in out
    assert "bobiverse-bob-worker" in out
    assert "bob/.grok/skills/bobiverse-bob-worker/SKILL.md" in out


def test_fr3317_intake_skills_visionary_opens_pr_there(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    # Seed empty skill book so filter_new_lessons opens a PR.
    filer.repo_files[".grok/skills/harvest-skills-visionary/SKILL.md"] = (
        "# harvest-skills-visionary\n\n"
    )
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": "SimonBarnett/skills-visionary",
            "title": "harvest: Plan-seat xlsx export playbook",
            "body": (
                "Session summary:\nPlan xlsx helpers\n\n"
                "Lessons:\n- Plan xlsx helpers belong with harvest-skills-visionary\n"
            ),
            "source": {
                "skill_book": "harvest-skills-visionary",
                "agent": "Invoke-BobiverseHarvest",
            },
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_fr3317_sv")
    assert rec["state"] == "filed"
    assert filer.prs, "expected lesson PR in skills-visionary"
    pr = filer.prs[-1]
    assert pr["repo"] == "SimonBarnett/skills-visionary"
    paths = [f.get("path") for f in (pr.get("files") or [])]
    assert ".grok/skills/harvest-skills-visionary/SKILL.md" in paths
    assert not any(
        str(p).replace("\\", "/").endswith("common/.grok/skills/harvest/SKILL.md")
        for p in paths
    )


def test_fr3317_missing_owner_holds_issue_not_pr(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": "SimonBarnett/iphone-text-bridge",
            "title": "harvest: Shortcuts all-SMS recipe",
            "body": (
                "Session summary:\niphone-text-bridge\n\n"
                "Lessons:\n- Shortcuts all-SMS recipe for the bridge\n"
            ),
            "source": {"skill_book": "harvest", "agent": "Invoke-BobiverseHarvest"},
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_fr3317_hold")
    assert rec["state"] == "held_owner_missing"
    assert rec.get("intended_owner") == "SimonBarnett/iphone-text-bridge"
    assert filer.prs == []
    assert filer.issues, "expected held bobiverse issue"
    issue = filer.issues[-1]
    assert issue["repo"] == "SimonBarnett/bobiverse"
    labs = {str(x).lower() for x in (issue.get("labels") or [])}
    assert intake.OWNER_MISSING_LABEL in labs
    # Not offerable as FR (label path).
    assert (
        gitclaim.issue_skip_fr_reason(
            title=issue["title"],
            body=issue.get("body") or "",
            labels=tuple(issue.get("labels") or ()),
        )
        == f"label:{intake.OWNER_MISSING_LABEL}"
    )
    # FR #3658: still not offerable if labels were dropped on create.
    assert (
        gitclaim.issue_skip_fr_reason(
            title=issue["title"],
            body=issue.get("body") or "",
            labels=(),
        )
        == "owner_missing_hold_title"
    )


def test_fr3317_job_mrb_short_triage_checklist():
    text = JOB_MRB.read_text(encoding="utf-8")
    assert "FR #3317" in text
    assert "Short triage checklist" in text
    assert "Useful?" in text
    assert "Generalised?" in text
    assert "Non-duplicate?" in text
    assert "Vision / AGENTS fit?" in text
    assert "not-useful" in text
    assert "no full test suite" in text.lower() or "Cost cap" in text


def test_fr3317_mrb_closed_not_useful_and_moved_are_verdicts():
    assert (
        gitclaim.issue_skip_fr_reason(
            title="MRB CLOSED - not-useful: one-box anecdote",
            labels=(),
        )
        == "mrb_verdict_title"
    )
    assert (
        gitclaim.issue_skip_fr_reason(
            title="MRB MOVED: SimonBarnett/a-search#610",
            labels=(),
        )
        == "mrb_verdict_title"
    )
    assert re.search(gitclaim.MRB_VERDICT_TITLE_RE, "MRB CLOSED - not-useful: x")
    assert re.search(gitclaim.MRB_VERDICT_TITLE_RE, "MRB MOVED - owner/repo#1")
