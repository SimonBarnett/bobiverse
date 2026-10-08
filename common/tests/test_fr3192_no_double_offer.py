# -*- coding: utf-8 -*-
"""FR #3192: do not double-offer the same queue row (one seat or two).

Acceptance that fails on pre-3192 main:
- Two seats !bored with one eligible row → exactly one offer (other empty/skip).
- Seat holding an unacked offer for X that !boreds again → not re-offered X (busy).
- release_stale_busy must not clear digest doing when the seat still has offered_to pending.
- Stale !bored after ACK: offer_focus_top / bored path must not hand a second row.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import bobreport
import gitclaim
import registered_machines


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("JEEVES_OWNER_ACCOUNT", "simon")
    for k in ("JEEVES_FOCUS_MUTATORS", "JEEVES_FOCUS_MUTATOR_ACCOUNTS"):
        monkeypatch.delenv(k, raising=False)
    registered_machines.save_registered(tmp_path, {"ionos", "marchhare"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def _row(repo, task, num, seq, **kw):
    r = {
        "repo": repo,
        "task": task,
        "id": f"#{num}",
        "seq": seq,
        "url": kw.pop("url", f"https://github.com/{repo}/issues/{num}"),
    }
    r.update(kw)
    return r


def _queue(home: Path, rows: list) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": rows, "accepted": [], "done": []},
    )


def test_fr3192_two_seats_one_row_exactly_one_offer(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _queue(home, [_row("o/a", "FR", 1, 1)])
    t0 = time.time()
    s1, j1 = gitclaim.offer_focus_top(home, "marchhare-100", "#marchhare", now=t0)
    s2, j2 = gitclaim.offer_focus_top(home, "marchhare-200", "#marchhare", now=t0 + 1)
    assert s1 == "ok" and j1 and j1["id"] == "#1"
    assert j1.get("offered_to") == "marchhare-100"
    # Second seat must not get the same row while the first offer is live.
    assert s2 == "empty" or (j2 is None) or (j2.get("id") != "#1")
    if s2 == "ok" and j2:
        assert j2.get("offered_to") != "marchhare-200" or j2["id"] != "#1"


def test_fr3192_same_seat_holding_offer_not_reoffered(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _queue(home, [_row("o/a", "FR", 1, 1), _row("o/a", "FR", 2, 2)])
    t0 = time.time()
    s1, j1 = gitclaim.offer_focus_top(home, "marchhare-100", "#marchhare", now=t0)
    assert s1 == "ok" and j1["id"] == "#1"
    # Second !bored while still holding unacked #1: must not rebroadcast #1.
    gate = gitclaim.bored_gate(home, "marchhare-100", "#marchhare", t0 + 5)
    assert gate == "busy", "pending offered_to must nak-busy, not re-offer"
    s2, j2 = gitclaim.offer_focus_top(home, "marchhare-100", "#marchhare", now=t0 + 5)
    # If offer_focus_top is reached, it must skip #1 (next row or empty) — never rebroadcast #1.
    if s2 == "ok" and j2:
        assert j2["id"] != "#1"


def test_fr3192_release_stale_busy_respects_pending_offer(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _queue(home, [_row("o/a", "FR", 3188, 1)])
    t0 = time.time()
    gitclaim.offer_focus_top(home, "marchhare-22372", "#marchhare", now=t0)
    # Digest may say doing (manual assign / on_ack) while the row is still only offered_to.
    # worker_list must also look busy or FR #1714 heals the legacy workers map to idle.
    doc = bobreport.empty_digest()
    doc["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    doc["machines"]["marchhare"]["workers"] = {
        "22372": {"state": "doing", "working_on": "FR o/a#3188"},
    }
    doc["machines"]["marchhare"]["worker_list"] = [
        {
            "nick": "marchhare-22372",
            "state": "doing",
            "working_on": "FR o/a#3188",
        }
    ]
    bobreport.save_digest(home, doc)
    assert gitclaim.seat_pending_offer(home, "marchhare-22372", t0 + 10)
    healed = gitclaim.release_stale_busy(home, "marchhare-22372", t0 + 10)
    assert healed is False, "must not clear doing while offered_to is still live"
    gate = gitclaim.bored_gate(home, "marchhare-22372", "#marchhare", t0 + 10)
    assert gate == "busy"


def test_fr3192_stale_bored_after_ack_skips_second_offer(tmp_path, monkeypatch):
    """After ACK, a late offer_focus_top for the same seat must not stamp a new row."""
    home = _home(tmp_path, monkeypatch)
    _queue(home, [_row("o/a", "FR", 1, 1), _row("o/b", "MRB", 2, 2, url="https://github.com/o/b/pull/2")])
    t0 = time.time()
    s1, j1 = gitclaim.offer_focus_top(home, "marchhare-1", "#marchhare", now=t0)
    assert s1 == "ok" and j1["id"] == "#1"
    st, acc = gitclaim.accept_offered(home, "marchhare-1", "#marchhare")
    assert st == "ok" and acc["id"] == "#1"
    # Stale !bored processing continues: gate must be busy (accepted), not ok with a new offer.
    gate = gitclaim.bored_gate(home, "marchhare-1", "#marchhare", t0 + 5)
    assert gate == "busy"
    # And should_drop_stale_bored (if present) reports True after ACK.
    drop = getattr(gitclaim, "should_drop_stale_bored", None)
    if drop is not None:
        assert drop(home, "marchhare-1", t0 + 5) is True


def test_fr3192_worker_held_assign_blocks_bored(tmp_path):
    """bob_worker: Relay held/inject_failed assign arms inject-pending so !bored stays quiet."""
    import sys
    from pathlib import Path as P

    root = P(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "bob" / "scripts"))
    import bob_worker as bw

    logs: list[str] = []
    relay = bw.Relay(logs.append, persist_dir=tmp_path)
    # No inject target → deliver holds the assign.
    status = relay.deliver("Jeeves", "#marchhare", "marchhare-1: FR o/a#9 https://github.com/o/a/issues/9")
    assert status == "held"
    assert relay.has_pending_work() is True

    sent: list[str] = []
    bored = bw.BoredEmitter(lambda: sent.append("!bored") or True, logs.append, idle_s=0.01, repeat_s=0.01)
    bored.relay = relay  # FR #3192 wiring
    bored.set_ready(True)
    # Force idle due immediately.
    bored._idle_since = bored.clock() - 10
    bored._start_sent = True
    reason = bored._reason(bored.clock())
    assert reason is None, "held assign must block !bored"
    assert sent == []
