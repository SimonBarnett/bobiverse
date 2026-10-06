"""FR #1812: harvest/skill intake with existing PR URL must not file fallback issue."""
from __future__ import annotations

import sys
from pathlib import Path

from repo_layout import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import gitclaim  # noqa: E402
import intake  # noqa: E402


class RaisingDraftFiler(intake.FakeGitHubFiler):
    """Match production GhCliFiler: draft PR always fails → old path filed issues."""

    def create_draft_pr(self, repo, title, body, branch, files, labels):
        raise RuntimeError("gh_filer: draft PR not implemented; use issue fallback")

    def create_pr(self, repo, title, body, branch, files, labels):
        # FR #2705 lesson path also needs a failing create_pr for queue tests.
        raise RuntimeError("gh_filer: create_pr not implemented; use issue fallback")


def _home(name: str) -> Path:
    p = ROOT / "tests" / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def test_fr1812_harvest_with_pr_url_links_no_issue():
    """No real Lessons + existing PR URL → linked_existing_pr (never a fallback issue)."""
    filer = RaisingDraftFiler()
    home = _home("_tmp_intake_fr1812_link")
    norm = {
        "kind": "harvest",
        "repo": "SimonBarnett/bobiverse",
        "title": "harvest: FR #1657 conflict-marker; PR opened",
        "body": (
            "Session summary:\nPR opened\n\nLessons:\n- (no new playbook line)\n\n"
            "https://github.com/SimonBarnett/bobiverse/pull/1794\n"
        ),
        "files": [],
        "source": {"machine": "marchhare", "agent": "Invoke-BobiverseHarvest", "skill_book": "harvest", "version": ""},
        "idempotency_key": "hv-fr1812-link1",
        "contact": "",
        "contact_public": False,
    }
    rec = intake.file_submission(home, norm, filer, intake_id="in_fr1812a")
    assert rec["state"] == "linked_existing_pr"
    assert rec["number"] == 1794
    assert "pull/1794" in rec["url"]
    assert filer.issues == []
    assert filer.prs == []


def test_fr1812_harvest_pr_url_with_lessons_opens_lesson_pr():
    """FR #2705: existing PR URL must not drop Lessons — open non-draft skill-book PR."""
    filer = intake.FakeGitHubFiler()
    filer.repo_files["common/.grok/skills/harvest/SKILL.md"] = "# Harvest\n"
    home = _home("_tmp_intake_fr1812_lesson")
    norm = {
        "kind": "harvest",
        "repo": "SimonBarnett/bobiverse",
        "title": "harvest: FR #1657 conflict-marker; PR opened",
        "body": (
            "Session summary:\nPR opened\n\nLessons:\n- conflict markers must be clean\n\n"
            "https://github.com/SimonBarnett/bobiverse/pull/1794\n"
        ),
        "files": [],
        "source": {"machine": "marchhare", "agent": "Invoke-BobiverseHarvest", "skill_book": "harvest", "version": ""},
        "idempotency_key": "hv-fr1812-lesson1",
        "contact": "",
        "contact_public": False,
    }
    rec = intake.file_submission(home, norm, filer, intake_id="in_fr1812lesson")
    assert rec["state"] == "filed"
    assert filer.issues == []
    assert filer.prs
    assert filer.prs[-1].get("draft") is False
    assert "harvest-lesson" in filer.prs[-1]["labels"]


def test_fr1812_harvest_without_pr_queues_not_issue_fallback():
    """MRB #2269 / follow-up #2181: harvest PR failure queues; never issue-fallback.

    FR #2705: lesson path uses create_pr; RaisingDraftFiler fails both create_pr and
    create_draft_pr so the queue path still covers GitHub-down.
    """
    import pytest

    filer = RaisingDraftFiler()
    home = _home("_tmp_intake_fr1812_issue")
    norm = {
        "kind": "harvest",
        "repo": "SimonBarnett/bobiverse",
        "title": "harvest: ear restart loop",
        "body": "Session summary:\near died\n\nLessons:\n- pass --host\n",
        "files": [],
        "source": {"machine": "flamingo", "agent": "Invoke-BobiverseHarvest", "skill_book": "harvest", "version": ""},
        "idempotency_key": "hv-fr1812-issue1",
        "contact": "",
        "contact_public": False,
    }
    with pytest.raises(intake.GitHubDown):
        intake.file_submission(home, norm, filer, intake_id="in_fr1812b")
    assert filer.issues == []
    assert (home / "intake" / "outbox" / "in_fr1812b.json").is_file()


def test_fr1812_draft_pr_exception_is_logged_on_record():
    filer = RaisingDraftFiler()
    home = _home("_tmp_intake_fr1812_log")
    norm = {
        "kind": "skill",
        "repo": "SimonBarnett/bobiverse",
        "title": "skill: something",
        "body": "lesson without pr link",
        "files": [],
        "source": {"machine": "x", "agent": "a", "skill_book": "harvest", "version": ""},
        "idempotency_key": "hv-fr1812-log1",
        "contact": "",
        "contact_public": False,
    }
    rec = intake.file_submission(home, norm, filer, intake_id="in_fr1812c")
    assert rec["state"] == "filed_issue_fallback"
    assert "draft_pr_error" in rec
    assert "draft PR not implemented" in str(rec["draft_pr_error"])


def test_fr1812_skip_fr_for_skill_summary_with_pr_url():
    reason = gitclaim.issue_skip_fr_reason(
        title="harvest: FR #1663 tray SkipTidy; PR https://github.com/SimonBarnett/bobiverse/pull/1796",
        body="Session summary:\nPR opened\n",
        labels=("via-intake", "skill"),
    )
    assert reason == "harvest_pr_summary"


def test_fr1812_skip_fr_for_pr_opened_title():
    reason = gitclaim.issue_skip_fr_reason(
        title="harvest: FR #1657 ... PR opened",
        body="no url here but title says opened",
        labels=("via-intake", "skill"),
    )
    assert reason == "harvest_pr_summary"


def test_fr1812_skill_without_pr_still_offerable():
    reason = gitclaim.issue_skip_fr_reason(
        title="harvest: promote ARP VERSION truth",
        body="Lessons:\n- ARP DisplayVersion\n",
        labels=("via-intake", "skill"),
    )
    assert reason is None
