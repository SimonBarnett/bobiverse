"""FR #2705: harvest Lessons land as non-draft skill-book PRs; receipts must not drop lessons."""
from __future__ import annotations

import json
from pathlib import Path

import gitclaim
import intake


REPO = "SimonBarnett/bobiverse"
HARVEST_SKILL = "common/.grok/skills/harvest/SKILL.md"
MRB_INSTRUCTION = "MRB (light triage): is the lesson useful, generalised, non-duplicate"


def _pr_opened_payload(
    *,
    number: int,
    title: str,
    body: str,
    draft: bool = False,
    labels: list[str] | None = None,
) -> dict:
    labs = [{"name": n} for n in (labels or [])]
    return {
        "action": "opened",
        "repository": {"full_name": REPO},
        "pull_request": {
            "number": number,
            "title": title,
            "body": body,
            "draft": draft,
            "html_url": f"https://github.com/{REPO}/pull/{number}",
            "labels": labs,
            "merged": False,
        },
    }


def test_fr2705_extract_harvest_lessons_ignores_placeholder():
    body = (
        "Session summary:\nDONE FR #1\n\nLessons:\n"
        "- Prefer durable worktree paths under C:\\ai\\\n"
        "- (no new playbook line)\n"
    )
    lessons = intake.extract_harvest_lessons(body)
    assert lessons == ["Prefer durable worktree paths under C:\\ai\\"]
    assert intake.extract_harvest_lessons("Session summary:\nnothing\n\nLessons:\n- (no new playbook line)\n") == []


def test_fr2705_resolve_skill_book_from_source_and_default():
    book, path = intake.resolve_skill_book(
        skill_book="harvest",
        title="harvest: session",
        body="Lessons:\n- x\n",
    )
    assert book == "harvest"
    assert path == HARVEST_SKILL
    book2, path2 = intake.resolve_skill_book(
        skill_book="",
        title="harvest: mrb hostile review playbook",
        body="Lessons:\n- hostile MRB must vision-first\n",
    )
    assert book2 == "bobiverse-bob-job-mrb"
    assert path2.endswith("bobiverse-bob-job-mrb/SKILL.md")
    book3, path3 = intake.resolve_skill_book(
        skill_book="",
        title="harvest: misc",
        body="Lessons:\n- generic tip\n",
    )
    assert book3 == "harvest"
    assert path3 == HARVEST_SKILL


def test_fr2705_apply_lessons_appends_heading():
    base = "# Harvest\n\nBody.\n"
    out = intake.apply_lessons_to_skill_md(base, ["First lesson", "Second lesson"])
    assert "## Harvested lessons (intake)" in out
    assert "- First lesson" in out
    assert "- Second lesson" in out
    again = intake.apply_lessons_to_skill_md(out, ["Third"])
    assert again.count("## Harvested lessons (intake)") == 1
    assert "- Third" in again


def test_fr2705_receipt_with_lessons_opens_non_draft_skill_pr(tmp_path: Path):
    """DONE/PASS receipt that still carries Lessons must open a non-draft SKILL.md PR."""
    filer = intake.FakeGitHubFiler()
    filer.repo_files[HARVEST_SKILL] = "# Harvest\n\nIntro.\n"
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: MRB #2642 PASS: merged PR #2642",
            "body": (
                "Session summary:\nMRB #2642 PASS: merged PR #2642\n\n"
                "Lessons:\n- EncodedCommand must silence ProgressPreference CLIXML\n"
            ),
            "source": {"skill_book": "harvest", "agent": "Invoke-BobiverseHarvest"},
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_lesson2705")
    assert rec["state"] == "filed"
    assert filer.prs, "expected a lesson PR"
    pr = filer.prs[-1]
    assert pr.get("draft") is False
    assert "harvest-lesson" in pr["labels"]
    assert str(pr["title"]).startswith("lesson(harvest):")
    assert MRB_INSTRUCTION in (pr.get("body") or "")
    paths = [f.get("path") for f in pr.get("files") or []]
    assert HARVEST_SKILL in paths
    assert not any(str(p).startswith("docs/intake-harvest") for p in paths)
    content = next(f["content"] for f in pr["files"] if f["path"] == HARVEST_SKILL)
    assert "## Harvested lessons (intake)" in content
    assert "EncodedCommand must silence ProgressPreference CLIXML" in content


def test_fr2705_pure_receipt_without_lessons_stays_receipt_recorded(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: MRB #2642 PASS: merged PR #2642",
            "body": (
                "Session summary:\nMRB #2642 PASS: merged\n\n"
                "Lessons:\n- (no new playbook line)\n"
                "_via-intake Invoke-BobiverseHarvest_"
            ),
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_pure2705")
    assert rec["state"] == "receipt_recorded"
    assert filer.prs == []
    assert filer.issues == []


def test_fr2705_existing_pr_url_with_lessons_still_opens_lesson_pr(tmp_path: Path):
    """linked_existing_pr must not drop Lessons (FR #1812 + #2705)."""
    filer = intake.FakeGitHubFiler()
    filer.repo_files[HARVEST_SKILL] = "# Harvest\n"
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: PR opened for FR #2698",
            "body": (
                "Session summary:\nPR opened https://github.com/SimonBarnett/bobiverse/pull/2708\n\n"
                "Lessons:\n- describe-launch must report the selected mode cwd\n"
            ),
            "source": {"skill_book": "harvest"},
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_link2705")
    assert rec["state"] == "filed"
    assert filer.prs
    pr = filer.prs[-1]
    assert pr.get("draft") is False
    assert "harvest-lesson" in pr["labels"]
    assert HARVEST_SKILL in [f.get("path") for f in pr["files"]]


def test_fr2705_gitclaim_offers_harvest_lesson_not_receipt():
    assert gitclaim.is_intake_harvest_receipt_pr(
        title="lesson(harvest): tip utf8",
        body="MRB: verify lesson placement\nSession summary:\nx",
        labels=["via-intake", "harvest-lesson"],
    ) is False
    claim = gitclaim.claim_from_payload(
        "pull_request",
        _pr_opened_payload(
            number=2706,
            title="lesson(harvest): tip utf8 write playbook",
            body=(
                f"MRB: {MRB_INSTRUCTION}, then merge.\n\n"
                "Session summary:\nplaybook\nLessons:\n- tip\n"
            ),
            draft=False,
            labels=["via-intake", "harvest-lesson"],
        ),
    )
    assert claim is not None
    assert claim.task == "MRB"
    assert claim.id == "#2706"
    # Draft harvest receipts still skipped.
    assert (
        gitclaim.claim_from_payload(
            "pull_request",
            _pr_opened_payload(
                number=99,
                title="harvest: MRB #1 PASS",
                body="Session summary:\nPASS\n_via-intake Invoke-BobiverseHarvest_",
                draft=True,
                labels=["via-intake", "skill"],
            ),
        )
        is None
    )


def test_fr2705_drain_source_dir_routes_held_lessons(tmp_path: Path):
    home = tmp_path / "home"
    hold = tmp_path / "outbox-hold-2583"
    hold.mkdir(parents=True)
    (home / "intake" / "outbox").mkdir(parents=True)
    (home / "intake" / "records").mkdir(parents=True)
    filer = intake.FakeGitHubFiler()
    filer.repo_files[HARVEST_SKILL] = "# Harvest\n"
    iid = "in_hold2705"
    norm = {
        "kind": "harvest",
        "repo": REPO,
        "title": "harvest: DONE FR #1 with lesson",
        "body": (
            "Session summary:\nDONE FR SimonBarnett/bobiverse#1\n\n"
            "Lessons:\n- Held outbox lessons must still land in SKILL.md\n"
        ),
        "source": {"skill_book": "harvest", "agent": "Invoke-BobiverseHarvest"},
        "idempotency_key": "hv-hold2705",
    }
    (hold / f"{iid}.json").write_text(
        json.dumps({"norm": norm, "intake_id": iid, "quarantine": False}) + "\n",
        encoding="utf-8",
    )
    stats = intake.drain_intake_outbox(home, filer, source_dir=hold)
    assert iid in stats.filed
    assert iid not in stats.recorded_receipt
    assert filer.prs
    pr = filer.prs[-1]
    assert pr.get("draft") is False
    assert "harvest-lesson" in pr["labels"]
    assert not (hold / f"{iid}.json").exists()


def test_fr2705_invoke_harvest_book_param_sets_skill_book():
    script = Path(__file__).resolve().parents[1] / "scripts" / "Invoke-BobiverseHarvest.ps1"
    text = script.read_text(encoding="utf-8")
    assert "[string]$Book" in text or "[string] $Book" in text
    assert "skill_book" in text
    # -Book value must drive source.skill_book (not a hard-coded 'harvest' only).
    assert "$Book" in text
    assert (
        "skill_book = $bookName" in text
        or "skill_book = $Book" in text
        or "skill_book=$Book" in text
    )


def test_fr2705_job_mrb_documents_harvest_lesson_review():
    skill = (
        Path(__file__).resolve().parents[2]
        / "bob"
        / ".grok"
        / "skills"
        / "bobiverse-bob-job-mrb"
        / "SKILL.md"
    )
    text = skill.read_text(encoding="utf-8")
    assert "harvest-lesson" in text.lower() or "Harvested lessons (intake)" in text
    assert "SKILL.md" in text
