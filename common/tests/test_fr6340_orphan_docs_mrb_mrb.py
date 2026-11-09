"""FR #6340: clean orphan docs/mrb pin (original merged) gets one MRB; parent-open still skipped."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

gitclaim = importlib.import_module("gitclaim")

SHA = "a2cba433" + "0" * 32
REPO = "SimonBarnett/bobiverse"


def _home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    return home


def _docs_mrb_pr(num: int = 6327, parent: int = 6319, **extra) -> dict:
    row = {
        "number": num,
        "title": f"docs/mrb-{parent}: hostile pins",
        "body": f"Refs SimonBarnett/bobiverse#{parent}\n\nAdditive hostile tests.",
        "html_url": f"https://github.com/{REPO}/pull/{num}",
        "state": "open",
        "draft": False,
        "auto_merge": None,
        "head": {"sha": SHA[:40], "ref": f"docs/mrb-{parent}"},
        "base": {"ref": "main"},
        "user": {"login": "u"},
        "labels": [],
        "checks": "success",
        "mergeable": True,
        "mergeable_state": "clean",
    }
    row.update(extra)
    return row


def _parent_open(parent: int = 6319) -> dict:
    return {
        "number": parent,
        "title": f"FR product #{parent}",
        "html_url": f"https://github.com/{REPO}/pull/{parent}",
        "state": "open",
        "draft": False,
        "head": {"sha": "b" * 40, "ref": f"fr-{parent}"},
        "base": {"ref": "main"},
        "labels": [],
    }


def _resync(home: Path, open_prs: list, details: dict | None = None) -> list:
    details = details or {int(p["number"]): p for p in open_prs}

    def fetch_json(url: str):
        u = str(url or "")
        for n, det in details.items():
            if f"/pulls/{n}" in u and "/pulls?" not in u:
                return det
        if "/pulls" in u and "state=closed" not in u:
            return list(open_prs)
        if "/issues" in u:
            return []
        return []

    gitclaim.resync_from_github(home, [REPO], fetch_json=fetch_json)
    q = gitclaim.load_queue(home)
    return list(q.get("unaccepted") or []) + list(q.get("accepted") or [])


def test_fr6340_docs_mrb_parent_id_from_head_and_title():
    assert gitclaim.docs_mrb_pin_parent_pr_id(head_ref="docs/mrb-6319") == "#6319"
    assert gitclaim.docs_mrb_pin_parent_pr_id(title="docs/mrb-6324: pins") == "#6324"
    assert gitclaim.docs_mrb_pin_parent_pr_id(title="FR #1", head_ref="fr-1") == ""


def test_fr6340_clean_orphan_pin_queues_mrb(tmp_path: Path):
    """Acceptance 1: original merged (not in open set) + clean pin -> one MRB."""
    home = _home(tmp_path)
    pin = _docs_mrb_pr()
    rows = _resync(home, [pin], {6327: pin})
    jobs = [
        r
        for r in rows
        if str(r.get("task") or "").upper() == "MRB"
        and "6327" in str(r.get("id") or r.get("url") or "")
    ]
    assert len(jobs) == 1, rows
    assert jobs[0].get("docs_mrb_orphan") in (True, "1", 1, "true", "True")
    assert gitclaim.mrb_row_offerable(jobs[0]) is True
    assert gitclaim.mrb_row_not_offerable_reason(jobs[0]) is None


def test_fr6340_clean_pin_parent_still_open_skipped(tmp_path: Path):
    """Acceptance 2: parent still open -> keep FR #5500 skip."""
    home = _home(tmp_path)
    pin = _docs_mrb_pr()
    parent = _parent_open()
    rows = _resync(home, [pin, parent], {6327: pin, 6319: parent})
    jobs = [
        r
        for r in rows
        if "6327" in str(r.get("id") or r.get("url") or "")
        and str(r.get("task") or "").upper() in ("MRB", "FIX")
    ]
    assert jobs == [], rows


def test_fr6340_dirty_orphan_still_fix(tmp_path: Path):
    """Acceptance 4: DIRTY orphan still FIX (#6044)."""
    home = _home(tmp_path)
    pin = _docs_mrb_pr(mergeable=False, mergeable_state="dirty")
    rows = _resync(home, [pin], {6327: pin})
    jobs = [
        r
        for r in rows
        if str(r.get("task") or "").upper() == "FIX"
        and "6327" in str(r.get("id") or r.get("url") or "")
    ]
    assert jobs, rows
    mrb = [r for r in rows if str(r.get("task") or "").upper() == "MRB" and "6327" in str(r.get("id") or "")]
    assert mrb == []


def test_fr6340_pin_of_pin_still_skipped(tmp_path: Path):
    """Acceptance 3: pin-of-pin / lesson-of-lesson still skipped."""
    home = _home(tmp_path)
    pin = _docs_mrb_pr(
        num=6400,
        parent=6327,
        title="docs/mrb-6327: pin harvest skip after harvest-lesson MRB",
        body=(
            "Refs SimonBarnett/bobiverse#6327\n"
            "FAIL-supersede / light-triage pin of pin process-loop.\n"
        ),
        head={"sha": SHA[:40], "ref": "docs/mrb-6327"},
    )
    assert gitclaim.is_lesson_of_lesson_pr(
        title=pin["title"], body=pin["body"], head_ref=pin["head"]["ref"]
    )
    rows = _resync(home, [pin], {6400: pin})
    jobs = [
        r
        for r in rows
        if "6400" in str(r.get("id") or r.get("url") or "")
        and str(r.get("task") or "").upper() in ("MRB", "FIX")
    ]
    assert jobs == [], rows


def test_fr6340_webhook_orphan_claims_mrb():
    """Acceptance 1 (webhook): opened orphan pin claims MRB when parent not open."""
    def parent_open(_repo: str, _num: str) -> bool:
        return False

    claim = gitclaim.claim_from_payload(
        "pull_request",
        {
            "action": "opened",
            "repository": {"full_name": REPO},
            "pull_request": {
                "number": 6327,
                "title": "docs/mrb-6319: hostile pins",
                "body": "Refs #6319",
                "draft": False,
                "html_url": f"https://github.com/{REPO}/pull/6327",
                "head": {"ref": "docs/mrb-6319", "sha": SHA[:40]},
                "labels": [],
            },
        },
        docs_mrb_parent_open=parent_open,
    )
    assert claim is not None
    assert claim.task == "MRB"
    assert claim.id == "#6327"


def test_fr6340_webhook_parent_open_still_none():
    def parent_open(_repo: str, _num: str) -> bool:
        return True

    claim = gitclaim.claim_from_payload(
        "pull_request",
        {
            "action": "opened",
            "repository": {"full_name": REPO},
            "pull_request": {
                "number": 6327,
                "title": "docs/mrb-6319: hostile pins",
                "body": "Refs #6319",
                "draft": False,
                "html_url": f"https://github.com/{REPO}/pull/6327",
                "head": {"ref": "docs/mrb-6319", "sha": SHA[:40]},
                "labels": [],
            },
        },
        docs_mrb_parent_open=parent_open,
    )
    assert claim is None


def test_fr6340_queued_docs_mrb_row_is_offerable():
    """FR #6340: once queued, offer must not refuse docs_mrb_pin."""
    row = {
        "task": "MRB",
        "repo": REPO,
        "id": "#6327",
        "url": f"https://github.com/{REPO}/pull/6327",
        "title": "docs/mrb-6319: hostile pins",
        "head": "docs/mrb-6319",
        "state": "open",
    }
    assert gitclaim.mrb_row_not_offerable_reason(row) is None
    assert gitclaim.mrb_row_offerable(row) is True


def test_fr6340_assign_enqueue_docs_mrb_pin(tmp_path: Path):
    """Acceptance 7: !assign / enqueue_open_github_item offers a clean docs/mrb pin."""
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    doc = gitclaim.load_queue(home)
    pin = _docs_mrb_pr()

    def fetch_issue(_repo, _num):
        return {
            "number": 6327,
            "title": pin["title"],
            "body": pin["body"],
            "state": "open",
            "html_url": pin["html_url"],
            "pull_request": {},
            "draft": False,
            "labels": [],
        }

    status, detail = gitclaim.enqueue_open_github_item(
        doc, REPO, "MRB", "6327", fetch_issue=fetch_issue, home=home
    )
    assert status == "added", (status, detail)
    rows = [r for r in (doc.get("unaccepted") or []) if r.get("id") == "#6327"]
    assert rows
    assert gitclaim.mrb_row_offerable(rows[0]) is True


def test_fr6340_resync_fills_open_pr_queue_gap(tmp_path: Path):
    """Acceptance 8: resync queues an open PR that has no live queue row."""
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    product = {
        "number": 6401,
        "title": "FR #6400: product tip",
        "body": "Closes SimonBarnett/bobiverse#6400",
        "html_url": f"https://github.com/{REPO}/pull/6401",
        "state": "open",
        "draft": False,
        "auto_merge": None,
        "head": {"sha": SHA[:40], "ref": "fr-6400"},
        "base": {"ref": "main"},
        "user": {"login": "u"},
        "labels": [],
        "checks": "success",
        "mergeable": True,
        "mergeable_state": "clean",
    }
    before = gitclaim.load_queue(home)
    assert not any(
        "6401" in str(r.get("id") or "") for r in (before.get("unaccepted") or [])
    )
    rows = _resync(home, [product], {6401: product})
    jobs = [
        r
        for r in rows
        if str(r.get("task") or "").upper() == "MRB"
        and "6401" in str(r.get("id") or "")
    ]
    assert len(jobs) == 1, rows


def test_fr6340_giveup_keeps_row_offerable_for_other_seat():
    """Acceptance 9: GIVEUP blocks that seat only; the open PR row stays offerable."""
    row = {
        "task": "MRB",
        "repo": REPO,
        "id": "#6327",
        "url": f"https://github.com/{REPO}/pull/6327",
        "title": "docs/mrb-6319: hostile pins",
        "head": "docs/mrb-6319",
        "state": "open",
        "docs_mrb_orphan": "1",
        "giveup_seats": "redqueen-1",
    }
    assert gitclaim.mrb_row_not_offerable_reason(row) is None
    assert gitclaim.mrb_row_offerable(row) is True
    assert gitclaim.nick_in_giveup_seats(row, "redqueen-1") is True
    assert gitclaim.nick_in_giveup_seats(row, "redqueen-2") is False