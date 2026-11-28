"""FR #9919: cross-job GIVEUP must not wire; DONE must drain after turn_ended."""
from __future__ import annotations

import time

import bob_worker as bw
from repo_layout import ROOT
IDLE, REPEAT = 0.05, 0.05


class _Seat:
    shop = "#redqueen"

    def __init__(self):
        self.wire: list[str] = []

    def say(self, target: str, text: str) -> bool:
        self.wire.append(text.strip())
        return True


def _may_send(emitter: bw.BoredEmitter, payload: str):
    r = emitter.outbox_ack_refuse_reason(payload)
    if r:
        return (False, r)
    r = emitter.outbox_free_refuse_reason(payload)
    if r:
        return (False, r)
    return True


def test_fr9919_cross_job_giveup_not_wired_done_still_sends(tmp_path):
    """Wrong GIVEUP while ACK on #9903 must not hit IRC; real DONE still sends."""
    seat = _Seat()
    logs: list[str] = []
    e = bw.BoredEmitter(
        lambda: True,
        logs.append,
        idle_s=IDLE,
        repeat_s=REPEAT,
        harvest_hold_s=0.0,
    )
    e.start()
    e.set_ready(True)
    e.on_outbox("ACK MRB SimonBarnett/bobiverse#9903")
    ob = tmp_path / "outbox.txt"
    ob.write_text(
        "GIVEUP MRB SimonBarnett/bobiverse#9756\n"
        "DONE MRB SimonBarnett/bobiverse#9903 PASS https://example.com/p/9\n",
        encoding="utf-8",
    )
    n = bw.drain_outbox(ob, seat, logs.append, e.on_outbox, lambda p: _may_send(e, p))
    assert n == 1
    assert seat.wire == [
        "DONE MRB SimonBarnett/bobiverse#9903 PASS https://example.com/p/9",
    ]
    assert any("cross-job GIVEUP holding" in m for m in logs)
    assert any("ignore free-rx (GIVEUP)" in m for m in logs)
    e.stop()


def test_fr9919_outbox_free_refuse_reason_unit():
    e = bw.BoredEmitter(lambda: True, lambda _m: None, harvest_hold_s=0.0)
    e.start()
    e.set_ready(True)
    e.on_outbox("ACK FR SimonBarnett/bobiverse#1562")
    reason = e.outbox_free_refuse_reason("GIVEUP MRB SimonBarnett/bobiverse#1725")
    assert reason == "cross-job GIVEUP holding FR SimonBarnett/bobiverse#1562"
    assert e.outbox_free_refuse_reason("GIVEUP FR SimonBarnett/bobiverse#1562") is None
    e.stop()


def test_fr9919_supervisor_drain_run_outbox_now_wired():
    """Grok/opencode flush before turn_ended (FR #9919 / #10368).

    Cursor and Aider also flush (FR #10362). Those watchers drain after
    turn_ended so a DONE written on turn_ended still reaches IRC before the
    harvest !bored fire.
    """
    src = (ROOT / "scripts" / "bob_worker.py").read_text(encoding="utf-8")
    assert "def drain_run_outbox_now" in src
    needle = 'self.drain_run_outbox_now("turn_ended")'
    assert src.count(needle) == 3
    cursor_block = src.split("def _start_cursor_turn_watcher", 1)[1].split(
        "def _start_aider_turn_watcher", 1
    )[0]
    aider_block = src.split("def _start_aider_turn_watcher", 1)[1].split(
        "def _start_turn_watcher", 1
    )[0]
    assert needle in cursor_block
    assert needle in aider_block
    assert cursor_block.find("self.bored.turn_ended(") < cursor_block.find(needle)
    assert aider_block.find("self.bored.turn_ended(") < aider_block.find(needle)
    start = src.split("def _start_turn_watcher", 1)[1]
    block = start.split("def _on_inject", 1)[0]
    drain_at = block.find(needle)
    ended_at = block.find("self.bored.turn_ended(")
    assert drain_at != -1 and ended_at != -1
    assert drain_at < ended_at
