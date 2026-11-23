# -*- coding: utf-8 -*-
"""FR #8837 / BOB-G1 S1: offer respects digest hold/unhold.

Skip when a Depends-on digest has hold; fr-digest without hold satisfies while
OPEN; ordinary OPEN depends still skip (BOB-D3).
"""
from __future__ import annotations

from pathlib import Path

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines
import pytest


REPO = "SimonBarnett/bobiverse"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"marchhare", "flamingo"})
    digest = bobreport.empty_digest()
    for mid, pids in (
        ("marchhare", ("35600", "35601", "35602")),
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


def test_fr8837_skips_when_digest_held(home: Path):
    """S1 fail-when: must not offer while Depends-on fr-digest still has hold."""
    me = "marchhare-35600"
    digest = _row(
        REPO,
        "FR",
        9147,
        seq=1,
        title="Digest: go-gate",
        labels=["feature-request", "fr-digest", "hold"],
        body="fr-digest batch\n",
    )
    child = _row(
        REPO,
        "FR",
        8837,
        seq=2,
        body="Depends-on: #9147\nImplement S1.\n",
    )
    later = _row(REPO, "FR", 9, seq=3)
    _write(home, unaccepted=[digest, child, later])
    fi.handle_focus_cmd(home, REPO)

    st, job = gitclaim.offer_focus_top(home, me, "#marchhare")
    assert st == "ok" and job is not None
    assert job["id"] == "#9"

    doc = gitclaim.load_queue(home)
    blocked = next(r for r in doc["unaccepted"] if r.get("id") == "#8837")
    assert not str(blocked.get("offered_to") or "").strip()
    why = gitclaim.row_fr_depends_blocked_reason(child, doc)
    assert why and gitclaim.DEPENDS_HELD_REASON in why
    why2 = gitclaim.row_depends_open_reason(child, gitclaim.open_fr_issue_keys(doc), doc=doc)
    assert why2 == gitclaim.DEPENDS_HELD_REASON


def test_fr8837_fr_digest_open_without_hold_offers(home: Path):
    """S1: unhold digest — fr-digest OPEN without hold satisfies; child is offered."""
    me = "marchhare-35600"
    # Digest stays OPEN in accepted (not an offer candidate); child Depends-on it.
    digest = _row(
        REPO,
        "FR",
        9147,
        seq=1,
        title="Digest: go-gate",
        labels=["feature-request", "fr-digest"],
        body="fr-digest batch unheld\n",
    )
    digest["nick"] = "marchhare-35601"
    digest["accepted_ts"] = "2026-10-01T10:00:00Z"
    child = _row(
        REPO,
        "FR",
        8837,
        seq=2,
        body="Depends-on: #9147\nImplement S1.\n",
    )
    _write(home, unaccepted=[child], accepted=[digest])
    fi.handle_focus_cmd(home, REPO)

    st, job = gitclaim.offer_focus_top(home, me, "#marchhare")
    assert st == "ok" and job is not None
    assert job["id"] == "#8837"
    doc = gitclaim.load_queue(home)
    assert gitclaim.row_fr_depends_blocked_reason(child, doc) is None
    assert (
        gitclaim.row_depends_open_reason(child, gitclaim.open_fr_issue_keys(doc), doc=doc)
        is None
    )


def test_fr8837_bob_d3_still_blocks_plain_open_depend(home: Path):
    """Ordinary OPEN depend (no fr-digest) still skips (BOB-D3 preserved)."""
    me = "marchhare-35600"
    dep = _row(REPO, "FR", 5, seq=1)
    dep["nick"] = "marchhare-35601"
    dep["accepted_ts"] = "2026-10-01T10:00:00Z"
    blocked = _row(REPO, "FR", 3, seq=2, body="Depends-on: #5\n")
    later = _row(REPO, "FR", 9, seq=3)
    _write(home, unaccepted=[blocked, later], accepted=[dep])
    fi.handle_focus_cmd(home, REPO)

    st, job = gitclaim.offer_focus_top(home, me, "#marchhare")
    assert st == "ok" and job is not None
    assert job["id"] == "#9"


def test_fr8837_marker_for_monitor_soft_ok():
    """Monitor product_on_tip looks for bob_g1_skip_held_digest in gitclaim."""
    text = Path(gitclaim.__file__).read_text(encoding="utf-8")
    assert "bob_g1_skip_held_digest" in text
    assert gitclaim.DEPENDS_HELD_REASON == "depends-held"
