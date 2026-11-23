# -*- coding: utf-8 -*-
"""FR #8809 / BOB-D5 S1: fail closed on unresolved Depends-on refs."""
from __future__ import annotations

from pathlib import Path

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines
import pytest


REPO = "SimonBarnett/bobiverse"
OTHER = "SimonBarnett/other"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Chair home with registered machines + live seats (BOB_DIGEST_HOME for seat roster)."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"marchhare", "ionos", "flamingo"})
    digest = bobreport.empty_digest()
    for mid, pids in (
        ("marchhare", ("35600", "35601", "35602", "35603", "35604")),
        ("flamingo", ("9",)),
    ):
        digest["machines"][mid] = bobreport._empty_machine(mid)
        digest["machines"][mid]["worker_list"] = [
            {
                "nick": f"{mid}-{p}",
                "state": "idle",
                "kind": "grok",
                "start_model": "grok-4",
                "configured_model": "grok-4",
                "updated": "2026-11-17T12:00:00Z",
            }
            for p in pids
        ]
    bobreport.save_digest(tmp_path, digest)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return tmp_path


def _row(repo: str, task: str, num: int, seq: int | None = None, **kw) -> dict:
    r = {
        "repo": repo,
        "task": task,
        "id": f"#{num}",
        "seq": seq if seq is not None else num + 1000,
        "ts": f"2026-10-01T10:00:{num:02d}Z",
        "line": f"{task} {repo}#{num}",
        "url": f"https://github.com/{repo}/{'pull' if task == 'MRB' else 'issues'}/{num}",
        "title": f"{task} {num}",
        "state": "open",
    }
    r.update(kw)
    return r


def _write(home: Path, *, unaccepted: list[dict], accepted: list[dict] | None = None) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": unaccepted,
            "accepted": list(accepted or []),
            "done": [],
            "workers": {},
        },
    )


def test_fr8809_reason_constant_and_unit_bad_ref():
    """S1 unit: bad token / lookup failure → depends-unresolved; (none) stays clear."""
    assert gitclaim.DEPENDS_UNRESOLVED_REASON == "depends-unresolved"
    none_row = _row(REPO, "FR", 11, body="Depends-on: (none)\n")
    assert gitclaim.row_depends_open_reason(none_row, set()) is None

    bad = _row(REPO, "FR", 12, body="Depends-on: not-a-valid-ref\n")
    assert (
        gitclaim.row_depends_open_reason(bad, set())
        == gitclaim.DEPENDS_UNRESOLVED_REASON
    )

    mixed = _row(
        REPO,
        "FR",
        13,
        body="Depends-on: #40404, garbage-token\n",
    )
    assert (
        gitclaim.row_depends_open_reason(mixed, set())
        == gitclaim.DEPENDS_UNRESOLVED_REASON
    )

    def boom(repo: str, num: str) -> bool:
        raise gitclaim.GitHubLookupUnknown("rate")

    cross = _row(
        REPO,
        "FR",
        14,
        body="Depends-on: SimonBarnett/other#77\n",
    )
    assert (
        gitclaim.row_depends_open_reason(cross, set(), issue_open=boom)
        == gitclaim.DEPENDS_UNRESOLVED_REASON
    )


def test_fr8809_bad_ref_skips_offers_later_fr(home: Path):
    """S1: FR with malformed Depends-on is skipped; later FR is offered."""
    me = "marchhare-35600"
    blocked = _row(REPO, "FR", 3, seq=1, body="Depends-on: backlog-xyz\n")
    later = _row(REPO, "FR", 9, seq=2)
    _write(home, unaccepted=[blocked, later])
    fi.handle_focus_cmd(home, REPO)

    st, job = gitclaim.offer_focus_top(home, me, "#marchhare")
    assert st == "ok" and job is not None
    assert job["id"] == "#9"

    doc = gitclaim.load_queue(home)
    un_ids = {str(r.get("id")) for r in (doc.get("unaccepted") or [])}
    assert "#3" in un_ids
    blocked_row = next(r for r in doc["unaccepted"] if r.get("id") == "#3")
    assert not str(blocked_row.get("offered_to") or "").strip()


def test_fr8809_issue_open_unknown_blocks(home: Path, monkeypatch: pytest.MonkeyPatch):
    """Budgeted issue_open raising GitHubLookupUnknown → depends-unresolved skip."""
    monkeypatch.setattr(gitclaim, "BORED_GITHUB_CALL_BUDGET", 2)
    me = "marchhare-35600"
    blocked = _row(
        REPO,
        "FR",
        3,
        seq=1,
        body="Depends-on: SimonBarnett/other#77\n",
    )
    later = _row(REPO, "FR", 9, seq=2)
    _write(home, unaccepted=[blocked, later])
    fi.handle_focus_cmd(home, REPO)

    def issue_open(repo: str, num: str) -> bool:
        raise gitclaim.GitHubLookupUnknown("budget")

    st, job = gitclaim.offer_focus_top(
        home, me, "#marchhare", issue_open=issue_open
    )
    assert st == "ok" and job is not None
    assert job["id"] == "#9"
    left = {r["id"] for r in gitclaim.load_unaccepted(home)}
    assert "#3" in left


def test_fr8809_only_unresolved_empty_and_summarize(home: Path):
    """Only-unresolved queue → empty; summarize/format carry depends-unresolved."""
    me = "marchhare-35600"
    blocked = _row(REPO, "FR", 3, seq=1, body="Depends-on: ??bad??\n")
    _write(home, unaccepted=[blocked])
    fi.handle_focus_cmd(home, REPO)

    st, job = gitclaim.offer_focus_top(home, me, "#marchhare")
    assert st == "empty" and job is None

    stats = gitclaim.summarize_empty_offer(home, me)
    skips = stats.get("skips") or []
    assert {
        "key": f"FR {REPO}#3",
        "reason": gitclaim.DEPENDS_UNRESOLVED_REASON,
    } in skips
    detail = gitclaim.format_empty_offer_detail(me, stats)
    assert gitclaim.DEPENDS_UNRESOLVED_REASON in detail


def test_fr8809_none_still_offers(home: Path):
    """Depends-on: (none) remains offerable (not unresolved)."""
    me = "marchhare-35600"
    none_row = _row(REPO, "FR", 11, seq=1, body="Depends-on: (none)\n")
    _write(home, unaccepted=[none_row])
    fi.handle_focus_cmd(home, REPO)

    st, job = gitclaim.offer_focus_top(home, me, "#marchhare")
    assert st == "ok" and job is not None
    assert job["id"] == "#11"
