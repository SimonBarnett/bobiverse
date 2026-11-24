"""FR #9402: clear offered_to ghosts on hold / non-offerable; stuck-sweep releases idle pins.

Incident: ops tracker #9376 offered to flamingo-4120; seat went idle without ACK;
hold was labeled; !sweep/!stuck left offered_to so !assign refused busy.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import gitclaim
import stuck_job_sweep as sweep

REPO = "SimonBarnett/bobiverse"
OPS_BODY = (
    "## Status\n"
    "- **Ops install NOT done.**\n\n"
    "## CAST IRON (closing rule)\n"
    "Do **not** `Closes` this issue (or any walrus rebuild/install tracker) while "
    "Depends-on / GateIssues are still **OPEN**.\n\n"
    "## Instructions for Jeeves MONITORING agent (YOU)\n\n"
    "You are the **MONITORING** agent on redqueen.\n\n"
    "### GateIssues (script defaults)\n"
    "- skills-visionary **#155** — **OPEN**\n"
)


def _iso(now: float) -> str:
    return datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _queue(home: Path, *, unaccepted=None, accepted=None) -> None:
    home.mkdir(parents=True, exist_ok=True)
    doc = {
        "unaccepted": list(unaccepted or []),
        "accepted": list(accepted or []),
        "done": [],
    }
    gitclaim.queue_path(home).write_text(json.dumps(doc), encoding="utf-8")


def test_ops_monitor_tracker_skip_fr_reason():
    why = gitclaim.issue_skip_fr_reason(
        title="After Depends-on: rebuild jeeves on walrus",
        body=OPS_BODY,
        labels=("via-intake", "feature-request"),
    )
    assert why == "ops_monitor_tracker"
    assert (
        gitclaim.issue_skip_fr_reason(
            title="FR: ordinary product work",
            body="Ship the installer.",
            labels=("feature-request",),
        )
        is None
    )


def test_label_hold_drops_offered_to_and_frees_seat(tmp_path: Path):
    """Webhook labeled hold must drop the unaccepted pin (not leave offered_to)."""
    home = tmp_path / "digest"
    now = 1_700_000_000.0
    nick = "flamingo-4120"
    _queue(
        home,
        unaccepted=[
            {
                "repo": REPO,
                "task": "FR",
                "id": "#9376",
                "title": "rebuild jeeves on walrus",
                "body": OPS_BODY,
                "labels": ["via-intake", "feature-request"],
                "offered_to": nick,
                "offered_ts": _iso(now - 30.0),
                "line": f"FR {REPO}#9376",
            }
        ],
    )
    gitclaim.note_seat_hold(
        home,
        nick,
        {
            "repo": REPO,
            "task": "FR",
            "id": "#9376",
        },
        via="offer",
    )
    assert gitclaim.seat_open_job(home, nick, now).startswith("offered")

    claim = gitclaim.GitClaim(
        repo=REPO,
        task="FR",
        id="9376",
        event="issues",
        action="labeled",
        line=f"https://github.com/{REPO}/issues/9376",
        title="rebuild jeeves on walrus",
        body=OPS_BODY,
        labels=("via-intake", "feature-request", "hold"),
        state="open",
    )
    result = gitclaim.apply_queue_event(home, claim)
    assert result in ("removed", "updated", "noop")
    doc = gitclaim.load_queue(home)
    assert doc["unaccepted"] == []
    assert gitclaim.seat_open_job(home, nick, now) == ""


def test_label_hold_clears_offered_even_when_row_was_product_fr(tmp_path: Path):
    """Hold on a normal feature-request FR also clears offered_to (not ops-only)."""
    home = tmp_path / "digest"
    now = 1_700_000_000.0
    nick = "flamingo-99"
    _queue(
        home,
        unaccepted=[
            {
                "repo": REPO,
                "task": "FR",
                "id": "#100",
                "title": "FR: ship widget",
                "body": "Goal: ship widget.",
                "labels": ["feature-request"],
                "offered_to": nick,
                "offered_ts": _iso(now - 10.0),
            }
        ],
    )
    claim = gitclaim.GitClaim(
        repo=REPO,
        task="FR",
        id="100",
        event="issues",
        action="labeled",
        line="l",
        title="FR: ship widget",
        body="Goal: ship widget.",
        labels=("feature-request", "hold"),
        state="open",
    )
    gitclaim.apply_queue_event(home, claim)
    doc = gitclaim.load_queue(home)
    assert doc["unaccepted"] == []
    assert gitclaim.seat_open_job(home, nick, now) == ""


def test_unlabel_feature_request_on_ops_tracker_drops_pin(tmp_path: Path):
    """Losing feature-request on an ops/monitor tracker drops the ghost offer."""
    home = tmp_path / "digest"
    now = 1_700_000_000.0
    nick = "flamingo-4120"
    _queue(
        home,
        unaccepted=[
            {
                "repo": REPO,
                "task": "FR",
                "id": "#9376",
                "title": "rebuild jeeves on walrus",
                "body": OPS_BODY,
                "labels": ["via-intake", "feature-request", "hold"],
                "offered_to": nick,
                "offered_ts": _iso(now - 5.0),
            }
        ],
    )
    claim = gitclaim.GitClaim(
        repo=REPO,
        task="FR",
        id="9376",
        event="issues",
        action="unlabeled",
        line="l",
        title="rebuild jeeves on walrus",
        body=OPS_BODY,
        labels=("via-intake", "hold"),
        state="open",
    )
    gitclaim.apply_queue_event(home, claim)
    doc = gitclaim.load_queue(home)
    assert doc["unaccepted"] == []
    assert gitclaim.seat_open_job(home, nick, now) == ""


def test_stuck_sweep_releases_offered_on_held_row(tmp_path: Path):
    """!stuck/!sweep must clear offered_to on a held unaccepted row (released>0)."""
    home = tmp_path / "digest"
    now = 1_700_000_000.0
    nick = "flamingo-4120"
    _queue(
        home,
        unaccepted=[
            {
                "repo": REPO,
                "task": "FR",
                "id": "#9376",
                "title": "rebuild jeeves",
                "body": "Goal",
                "labels": ["hold", "feature-request"],
                "offered_to": nick,
                "offered_ts": _iso(now - 30.0),
                "ts": _iso(now - 3600.0),
            }
        ],
    )
    report = sweep.run_stuck_sweep(
        home,
        now=now,
        live={nick, "flamingo-19712"},
        idle={nick, "flamingo-19712"},
        activity={nick: now - 5.0},
        open_items=[],
        act=True,
    )
    assert int(report["actions"].get("released_offers") or 0) >= 1
    doc = gitclaim.load_queue(home)
    assert doc["unaccepted"] == []
    assert gitclaim.seat_open_job(home, nick, now) == ""


def test_stuck_sweep_releases_idle_no_ack_offer(tmp_path: Path):
    """Idle seat with aged offered_to and no ACK → clear pin (row stays offerable)."""
    home = tmp_path / "digest"
    now = 1_700_000_000.0
    nick = "flamingo-4120"
    age = float(gitclaim.OFFER_TIMEOUT_S) + 5.0
    _queue(
        home,
        unaccepted=[
            {
                "repo": REPO,
                "task": "FR",
                "id": "#9401",
                "title": "FR: real product",
                "body": "Ship it.",
                "labels": ["feature-request"],
                "offered_to": nick,
                "offered_ts": _iso(now - age),
                "ts": _iso(now - 3600.0),
            }
        ],
    )
    report = sweep.run_stuck_sweep(
        home,
        now=now,
        live={nick, "redqueen-1"},
        idle={nick, "redqueen-1"},
        activity={nick: now - 1.0},
        open_items=[],
        act=True,
    )
    assert int(report["actions"].get("released_offers") or 0) >= 1
    doc = gitclaim.load_queue(home)
    assert len(doc["unaccepted"]) == 1
    row = doc["unaccepted"][0]
    assert not str(row.get("offered_to") or "").strip()
    assert gitclaim.seat_open_job(home, nick, now) == ""


def test_seat_open_job_clears_aged_offer_before_busy(tmp_path: Path, monkeypatch):
    """seat_open_job (used by !assign) must clear aged un-ACKed offered_to first."""
    home = tmp_path / "digest"
    now = 1_700_000_000.0
    nick = "flamingo-4120"
    age = float(gitclaim.OFFER_TIMEOUT_S) + 10.0
    _queue(
        home,
        unaccepted=[
            {
                "repo": REPO,
                "task": "FR",
                "id": "#9376",
                "title": "old pin",
                "labels": ["feature-request"],
                "offered_to": nick,
                "offered_ts": _iso(now - age),
            }
        ],
    )
    monkeypatch.setattr(gitclaim, "live_seat_nicks", lambda *_a, **_k: {nick})
    # Fresh pin (age < timeout) still busy.
    fresh_home = tmp_path / "fresh"
    _queue(
        fresh_home,
        unaccepted=[
            {
                "repo": REPO,
                "task": "FR",
                "id": "#9376",
                "title": "fresh pin",
                "labels": ["feature-request"],
                "offered_to": nick,
                "offered_ts": _iso(now - 5.0),
            }
        ],
    )
    assert gitclaim.seat_open_job(fresh_home, nick, now).startswith("offered")
    # Aged pin is cleared; seat is free for !assign.
    assert gitclaim.seat_open_job(home, nick, now) == ""
    doc = gitclaim.load_queue(home)
    assert not str(doc["unaccepted"][0].get("offered_to") or "").strip()
