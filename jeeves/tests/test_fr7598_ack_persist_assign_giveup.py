# -*- coding: utf-8 -*-
"""FR #7598: persist received ACK; no second assign; missing GIVEUP skips ledger.

Acceptance:
1. ACK on a LOST_ACK_RESTART row clears the phantom stamp so !bored cannot
   requeue:LOST_ACK_NO_ACK after a real ACK arrived.
2. assign_row refuses a second job while the seat holds an accepted ACK.
3. GIVEUP whose lookup returns missing does not write a ledger giveup block.
Generic fixtures only (no host-specific names in assertions beyond seat grammar).
"""
from __future__ import annotations

import time
from pathlib import Path

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines
import shop_listen

REPO = "acme/widgets"
NICK = "flamingo-9001"
SHOP = "#flamingo"
OTHER = "acme/widgets#42"


def _seed(home: Path, monkeypatch) -> None:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(home, {"flamingo"})
    dig = bobreport.empty_digest()
    dig["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    dig["machines"]["flamingo"]["workers"] = {
        "9001": {"pid": "9001", "nick": NICK, "state": "idle", "working_on": ""}
    }
    dig["machines"]["flamingo"]["worker_list"] = [
        {
            "nick": NICK,
            "state": "idle",
            "work": "",
            "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    ]
    bobreport.save_digest(home, dig)
    fi.handle_focus_cmd(home, REPO)


def _row(num: int = 41, **extra) -> dict:
    base = {
        "repo": REPO,
        "task": "FR",
        "id": f"#{num}",
        "seq": num,
        "ts": "2026-11-15T17:00:00Z",
        "line": f"FR {REPO}#{num}",
        "title": f"fr {num}",
        "url": f"https://github.com/{REPO}/issues/{num}",
        "state": "open",
    }
    base.update(extra)
    return base


def _queue(home: Path, *, unaccepted=None, accepted=None, done=None) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": list(unaccepted or []),
            "accepted": list(accepted or []),
            "done": list(done or []),
        },
    )


def test_ack_clears_lost_ack_restart_so_bored_does_not_requeue(tmp_path, monkeypatch):
    """ACK on LOST_ACK_RESTART persists as a real accept; no LOST_ACK_NO_ACK demote."""
    _seed(tmp_path, monkeypatch)
    accepted_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 60))
    _queue(
        tmp_path,
        accepted=[
            _row(41, nick=NICK, accepted_ts=accepted_ts, reconcile="LOST_ACK_RESTART")
        ],
    )
    result = shop_listen.handle_shop_worker_line(
        tmp_path,
        nick=NICK,
        channel=SHOP,
        body=f"ACK FR {REPO}#41",
        post_fn=lambda _p: 204,
    )
    assert result.get("handled") is True
    assert result.get("status") in ("ok", "duplicate")
    q = gitclaim.load_queue(tmp_path)
    acc = q.get("accepted") or []
    assert len(acc) == 1
    assert str(acc[0].get("nick") or "") == NICK
    assert str(acc[0].get("id") or "") == "#41"
    # Real ACK must drop the phantom reconcile stamp.
    assert str(acc[0].get("reconcile") or "") != "LOST_ACK_RESTART"
    demoted = gitclaim.release_unacked_lost_ack(tmp_path, NICK, log=lambda _l: None)
    assert demoted is False
    q2 = gitclaim.load_queue(tmp_path)
    assert len(q2.get("accepted") or []) == 1
    assert not any(
        str(r.get("reconcile") or "") == "requeue:LOST_ACK_NO_ACK"
        for r in (q2.get("unaccepted") or [])
    )
    # Seat stays busy: a second job must not be assigned while the ACK holds.
    _queue(
        tmp_path,
        unaccepted=[_row(42)],
        accepted=list(q2.get("accepted") or []),
    )
    st, detail = gitclaim.assign_row(tmp_path, NICK, REPO, "FR", "42")
    assert st == "refused"
    assert "busy" in str(detail).lower()



def test_assign_refuses_second_job_while_accepted(tmp_path, monkeypatch):
    """Jeeves does not assign a second job to a seat with an accepted job."""
    _seed(tmp_path, monkeypatch)
    accepted_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 30))
    _queue(
        tmp_path,
        unaccepted=[_row(42)],
        accepted=[_row(41, nick=NICK, accepted_ts=accepted_ts)],
    )
    why = gitclaim.seat_open_job(tmp_path, NICK)
    assert why.startswith("accepted FR")
    st, detail = gitclaim.assign_row(tmp_path, NICK, REPO, "FR", "42")
    assert st == "refused"
    assert "busy" in str(detail).lower()
    q = gitclaim.load_queue(tmp_path)
    assert any(str(r.get("id")) == "#41" for r in (q.get("accepted") or []))
    assert any(str(r.get("id")) == "#42" for r in (q.get("unaccepted") or []))


def test_giveup_missing_does_not_ledger_block(tmp_path, monkeypatch):
    """GIVEUP with status=missing must not write a ledger giveup block."""
    _seed(tmp_path, monkeypatch)
    wakes: list = []
    import stall_callbacks

    monkeypatch.setattr(
        stall_callbacks,
        "emit_giveup",
        lambda home, **kw: wakes.append({"home": str(home), **kw}) or True,
    )
    _queue(tmp_path, unaccepted=[], accepted=[], done=[])
    result = shop_listen.handle_shop_worker_line(
        tmp_path,
        nick=NICK,
        channel=SHOP,
        body=f"GIVEUP FR {REPO}#41",
        post_fn=lambda _p: 204,
    )
    assert result.get("handled") is True
    assert result.get("status") == "missing"
    led = gitclaim.ledger_load(tmp_path)
    gu = (led.get("giveup") or {}).get(gitclaim._lkey(REPO, "#41")) or {}
    assert not gu or NICK.lower() not in {str(k).lower() for k in gu}
    # No Bob wake / idle paint for a job that was never found.
    assert wakes == []
    assert result.get("webhook") is None

def test_fr7598_irc_agent_skips_on_done_for_missing_giveup():
    """Chair must not WorkerTracker.on_done when shop-listen status is missing."""
    root = Path(__file__).resolve().parents[2]
    src = (root / "common" / "scripts" / "irc_agent.py").read_text(encoding="utf-8")
    # FR #7598 branch sits with the FR #6857 already-done guard.
    assert "missing-giveup-no-idle" in src
    assert 'status == "missing"' in src
    start = src.index("elif verb in (\"DONE\", \"NACK\", \"GIVEUP\"):")
    chunk = src[start : start + 900]
    assert "already-done" in chunk
    assert 'status == "missing"' in chunk
    assert "on_done" in chunk
