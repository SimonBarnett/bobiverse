# -*- coding: utf-8 -*-
"""FR #9857: Walk Depends-on on offer (cross-repo + multi-ref).

Shared predicate: ``depends_gate_reason`` / ``walk_depends_on_offer_reason``.
Fail-when: foreign OPEN ``owner/repo#N`` ignored -> offered early.
"""
from __future__ import annotations

from pathlib import Path

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines
import pytest

REPO = "SimonBarnett/bobiverse"
OTHER = "SimonBarnett/skills-visionary"
ME = "flamingo-9696"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": ME, "state": "idle", "work": "", "updated": "2026-11-24T21:00:00Z"},
    ]
    bobreport.save_digest(tmp_path, digest)
    fi.handle_focus_cmd(tmp_path, REPO)
    return tmp_path


def _fr(repo: str, num: int, body: str, **extra) -> dict:
    row = {
        "repo": repo,
        "task": "FR",
        "id": f"#{num}",
        "title": f"FR {num}",
        "body": body,
        "line": f"FR {repo}#{num}",
        "url": f"https://github.com/{repo}/issues/{num}",
        "state": "open",
        "ts": "2026-11-24T21:00:00Z",
        "seq": num,
    }
    row.update(extra)
    return row


def _queue(home: Path, rows: list[dict]) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": rows, "accepted": [], "done": [], "workers": {}},
    )


def test_fr9857_walk_alias_matches_depends_gate_reason():
    """Public FR-A name is the shared offer/assign/list predicate."""
    assert hasattr(gitclaim, "walk_depends_on_offer_reason")
    row = _fr(REPO, 9857, "Depends-on: #9856\n")
    doc = {"unaccepted": [row, _fr(REPO, 9856, "Digest\n", labels=["fr-digest"])], "accepted": [], "done": []}
    a = gitclaim.walk_depends_on_offer_reason(row, doc, open_keys=gitclaim.open_fr_issue_keys(doc))
    b = gitclaim.depends_gate_reason(row, doc, open_keys=gitclaim.open_fr_issue_keys(doc))
    assert a == b


def test_fr9857_multi_ref_one_open_blocks(home: Path):
    child = _fr(REPO, 100, "Depends-on: #10, #11\n")
    dep_open = _fr(REPO, 10, "still open\n")
    dep_closed_body = _fr(REPO, 11, "done\n", state="closed")
    # closed must not be in unaccepted open_keys — omit #11 from queue
    _queue(home, [child, dep_open])
    doc = gitclaim._load_queue_unlocked(home)
    why = gitclaim.walk_depends_on_offer_reason(
        child, doc, open_keys=gitclaim.open_fr_issue_keys(doc)
    )
    assert why == gitclaim.DEPENDS_OPEN_REASON, why


def test_fr9857_multi_ref_both_closed_allows(home: Path):
    child = _fr(REPO, 100, "Depends-on: #10, #11\n")
    _queue(home, [child])  # neither #10 nor #11 in open queue
    doc = gitclaim._load_queue_unlocked(home)

    def issue_open(repo: str, num: str) -> bool:
        return False

    why = gitclaim.walk_depends_on_offer_reason(
        child,
        doc,
        open_keys=gitclaim.open_fr_issue_keys(doc),
        issue_open=issue_open,
    )
    assert why is None, why


def test_fr9857_cross_repo_open_blocks(home: Path):
    child = _fr(REPO, 9857, f"Depends-on: {OTHER}#243\n")
    _queue(home, [child])
    doc = gitclaim._load_queue_unlocked(home)

    def issue_open(repo: str, num: str) -> bool:
        return gitclaim._repo_key(repo) == gitclaim._repo_key(OTHER) and str(num) == "243"

    why = gitclaim.walk_depends_on_offer_reason(
        child,
        doc,
        open_keys=gitclaim.open_fr_issue_keys(doc),
        issue_open=issue_open,
    )
    assert why == gitclaim.DEPENDS_OPEN_REASON, why


def test_fr9857_cross_repo_closed_allows(home: Path):
    child = _fr(REPO, 9857, f"Depends-on: {OTHER}#243\n")
    _queue(home, [child])
    doc = gitclaim._load_queue_unlocked(home)

    def issue_open(repo: str, num: str) -> bool:
        return False

    why = gitclaim.walk_depends_on_offer_reason(
        child,
        doc,
        open_keys=gitclaim.open_fr_issue_keys(doc),
        issue_open=issue_open,
    )
    assert why is None, why


def test_fr9857_fail_when_foreign_open_ignored(home: Path):
    """Without live issue_open, foreign OPEN is invisible — with checker it must block."""
    child = _fr(REPO, 9857, f"Depends-on: {OTHER}#244\n")
    _queue(home, [child])
    doc = gitclaim._load_queue_unlocked(home)
    open_keys = gitclaim.open_fr_issue_keys(doc)
    # Token-free path (no checker): foreign not in local queue => no block (known limit).
    why_blind = gitclaim.walk_depends_on_offer_reason(child, doc, open_keys=open_keys)
    assert why_blind is None
    # Offer path with checker: must not offer early.

    def issue_open(repo: str, num: str) -> bool:
        return gitclaim._repo_key(repo) == gitclaim._repo_key(OTHER) and str(num) == "244"

    why_live = gitclaim.walk_depends_on_offer_reason(
        child, doc, open_keys=open_keys, issue_open=issue_open
    )
    assert why_live == gitclaim.DEPENDS_OPEN_REASON, why_live


def test_fr9857_fail_closed_unresolved_when_checker_raises(home: Path):
    child = _fr(REPO, 9857, f"Depends-on: {OTHER}#999\n")
    _queue(home, [child])
    doc = gitclaim._load_queue_unlocked(home)

    def issue_open(repo: str, num: str) -> bool:
        raise RuntimeError("rate_limit")

    why = gitclaim.walk_depends_on_offer_reason(
        child,
        doc,
        open_keys=gitclaim.open_fr_issue_keys(doc),
        issue_open=issue_open,
    )
    assert why == gitclaim.DEPENDS_UNRESOLVED_REASON, why


def test_fr9857_offer_focus_skips_cross_repo_open(home: Path):
    child = _fr(REPO, 9857, f"Depends-on: {OTHER}#243\n")
    _queue(home, [child])

    def issue_open(repo: str, num: str) -> bool:
        return gitclaim._repo_key(repo) == gitclaim._repo_key(OTHER) and str(num) == "243"

    st, job = gitclaim.offer_focus_top(
        home,
        ME,
        "#flamingo",
        issue_open=issue_open,
    )
    assert st == "empty", (st, job)


def test_fr9857_assign_refuses_cross_repo_open(home: Path):
    child = _fr(REPO, 9857, f"Depends-on: {OTHER}#243\n")
    _queue(home, [child])

    def issue_open(repo: str, num: str) -> bool:
        return gitclaim._repo_key(repo) == gitclaim._repo_key(OTHER) and str(num) == "243"

    st, why = gitclaim.assign_row(
        home,
        ME,
        REPO,
        "FR",
        "#9857",
        issue_open=issue_open,
    )
    assert st == "refused", (st, why)
    assert "depends" in str(why).lower(), why


def test_fr9857_multi_and_cross_both_closed_offer_ok(home: Path):
    child = _fr(REPO, 200, f"Depends-on: #10, {OTHER}#243\n")
    _queue(home, [child])

    def issue_open(repo: str, num: str) -> bool:
        # Child FR stays OPEN; only Depends-on refs are CLOSED.
        if gitclaim._repo_key(repo) == gitclaim._repo_key(REPO) and str(num) == "200":
            return True
        return False

    st, job = gitclaim.offer_focus_top(
        home,
        ME,
        "#flamingo",
        issue_open=issue_open,
    )
    assert st == "ok", (st, job)
    assert job and str(job.get("id")) in ("#200", "200")
