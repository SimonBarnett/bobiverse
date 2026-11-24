# -*- coding: utf-8 -*-
"""FR #9858: Held digest gate cross-repo (BOB-G1 foreign label state).

Child in repo B must not be offered while a digest in repo A still has ``hold``.
Same ``depends_gate_reason`` / ``walk_depends_on_offer_reason`` predicate for
offer, assign, and ``!list`` / offerable_count.

Fail-when: child offered while A digest held.
"""
from __future__ import annotations

from pathlib import Path

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines
import stuck_job_sweep
import pytest

REPO = "SimonBarnett/bobiverse"
OTHER = "SimonBarnett/skills-visionary"
ME = "flamingo-9696"
FOREIGN_DIGEST = 9001


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


def _held_foreign_issue(_repo: str, _num: str) -> dict:
    return {
        "state": "open",
        "title": "Digest: foreign held",
        "body": "Kind: fr-digest\n",
        "labels": [
            {"name": "fr-digest"},
            {"name": "hold"},
            {"name": "digest"},
        ],
        "html_url": f"https://github.com/{OTHER}/issues/{FOREIGN_DIGEST}",
    }


def _unheld_foreign_issue(_repo: str, _num: str) -> dict:
    return {
        "state": "open",
        "title": "Digest: foreign unheld",
        "body": "Kind: fr-digest\n",
        "labels": [{"name": "fr-digest"}, {"name": "digest"}],
        "html_url": f"https://github.com/{OTHER}/issues/{FOREIGN_DIGEST}",
    }


def test_fr9858_foreign_held_via_issue_fetch_is_depends_held(home: Path):
    child = _fr(REPO, 9858, f"Depends-on: {OTHER}#{FOREIGN_DIGEST}\n")
    _queue(home, [child])
    doc = gitclaim._load_queue_unlocked(home)
    why = gitclaim.depends_gate_reason(
        child,
        doc,
        open_keys=gitclaim.open_fr_issue_keys(doc),
        issue_fetch=_held_foreign_issue,
    )
    assert why == gitclaim.DEPENDS_HELD_REASON, why


def test_fr9858_foreign_unheld_digest_allows(home: Path):
    child = _fr(REPO, 9858, f"Depends-on: {OTHER}#{FOREIGN_DIGEST}\n")
    _queue(home, [child])
    doc = gitclaim._load_queue_unlocked(home)
    why = gitclaim.depends_gate_reason(
        child,
        doc,
        open_keys=gitclaim.open_fr_issue_keys(doc),
        issue_fetch=_unheld_foreign_issue,
        issue_open=lambda r, n: False,
    )
    assert why is None, why


def test_fr9858_fail_when_child_offered_while_foreign_digest_held(home: Path):
    """Fail-when: offer must not succeed while foreign digest still has hold."""
    child = _fr(REPO, 9858, f"Depends-on: {OTHER}#{FOREIGN_DIGEST}\n")
    _queue(home, [child])

    st, job = gitclaim.offer_focus_top(
        home,
        ME,
        "#flamingo",
        fetch_issue=_held_foreign_issue,
        issue_open=lambda r, n: True,
    )
    assert st == "empty", (st, job)


def test_fr9858_assign_refuses_foreign_held(home: Path):
    child = _fr(REPO, 9858, f"Depends-on: {OTHER}#{FOREIGN_DIGEST}\n")
    _queue(home, [child])
    st, why = gitclaim.assign_row(
        home,
        ME,
        REPO,
        "FR",
        "#9858",
        fetch_issue=_held_foreign_issue,
        issue_open=lambda r, n: True,
    )
    assert st == "refused", (st, why)
    assert "depend" in str(why).lower(), why


def test_fr9858_queued_foreign_held_row_blocks_without_fetch(home: Path):
    """Foreign digest present in the local queue with hold — token-free path."""
    child = _fr(REPO, 9858, f"Depends-on: {OTHER}#{FOREIGN_DIGEST}\n")
    foreign = _fr(
        OTHER,
        FOREIGN_DIGEST,
        "Kind: fr-digest\n",
        labels=["fr-digest", "hold", "digest"],
        title="Digest foreign held",
    )
    _queue(home, [child, foreign])
    doc = gitclaim._load_queue_unlocked(home)
    why = gitclaim.depends_gate_reason(
        child, doc, open_keys=gitclaim.open_fr_issue_keys(doc)
    )
    assert why == gitclaim.DEPENDS_HELD_REASON, why


def test_fr9858_offerable_count_excludes_foreign_held(home: Path):
    """Same predicate for digest offerable_count / !list ungated path."""
    child = _fr(REPO, 9858, f"Depends-on: {OTHER}#{FOREIGN_DIGEST}\n")
    foreign = _fr(
        OTHER,
        FOREIGN_DIGEST,
        "Kind: fr-digest\n",
        labels=["fr-digest", "hold", "digest"],
        title="Digest foreign held",
    )
    unrelated = _fr(REPO, 42, "Depends-on: (none)\n", title="unrelated parallel FR")
    # Keep foreign in the queue so token-free G1 sees hold; count only children.
    _queue(home, [child, foreign, unrelated])
    doc = gitclaim._load_queue_unlocked(home)
    offerable_rows = [child, unrelated]
    n = stuck_job_sweep.ungated_unaccepted_count(offerable_rows, doc=doc)
    assert n == 1, n
    assert stuck_job_sweep.ungated_unaccepted_count([child], doc=doc) == 0
