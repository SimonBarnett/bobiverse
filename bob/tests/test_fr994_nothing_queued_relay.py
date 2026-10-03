"""FR #994: Jeeves ``<nick>: nothing queued`` must reach the agent as FROM (or be explicitly logged).

Live bug: Halloy showed the reply but worker.log had no ``relay: injected`` and run_dir had no
last-from.txt, so operators thought the seat was deaf.
"""
from __future__ import annotations

import time
from pathlib import Path

import bob_worker as bw
from test_bob_worker_020 import Rig, ircd, make_seat, wait_until  # noqa: F401


NICK = "win-mpre8vi4u6u-22836"
SHOP = "#win-mpre8vi4u6u"
NQ = f"{NICK}: nothing queued"


def test_is_nothing_queued_helper():
    assert bw.is_nothing_queued(NQ, NICK)
    assert bw.is_nothing_queued("nothing queued", NICK)
    assert bw.is_nothing_queued(f"{NICK}, nothing queued", NICK)
    assert not bw.is_nothing_queued(f"{NICK}: FR o/r#1 https://x", NICK)
    assert not bw.is_nothing_queued(f"{NICK}: NAK !BORED wait", NICK)
    assert not bw.drop_text(NQ)


def test_relay_injects_nothing_queued_and_writes_last_from(tmp_path):
    logs: list[str] = []
    inj: list[str] = []
    r = bw.Relay(logs.append, persist_dir=tmp_path)
    r.set_target(lambda line: inj.append(line) or True)
    assert r.deliver("Jeeves", SHOP, NQ) == "injected"
    assert inj == [f"FROM Jeeves {SHOP} {NQ}"]
    assert any(m.startswith("relay: injected ") and "nothing queued" in m for m in logs)
    last = tmp_path / "last-from.txt"
    assert last.is_file()
    assert "nothing queued" in last.read_text(encoding="utf-8")


def test_relay_persists_last_from_even_when_inject_fails_for_nothing_queued(tmp_path):
    """Console inject can fail on an idle Grok TUI; operators still need last-from proof of the wire."""
    logs: list[str] = []
    r = bw.Relay(logs.append, persist_dir=tmp_path)
    r.set_target(lambda line: False)
    assert r.deliver("Jeeves", SHOP, NQ) == "inject_failed"
    last = tmp_path / "last-from.txt"
    assert last.is_file()
    assert "nothing queued" in last.read_text(encoding="utf-8")
    assert any("nothing-queued" in m and "inject failed" in m for m in logs)


def test_seat_relays_jeeves_nothing_queued_to_agent(ircd, tmp_path):
    seat = make_seat(ircd, machine="win-mpre8vi4u6u", pid=22836)
    assert seat.nick == NICK
    got: list[str] = []
    logs: list[str] = []
    relay = bw.Relay(logs.append, persist_dir=tmp_path / "run")
    relay.set_target(lambda line: got.append(line) or True)
    seat.on_message = relay.deliver
    seat.connect(timeout=5)
    ircd.send(f":Jeeves!j@h PRIVMSG {SHOP} :{NQ}")
    assert wait_until(lambda: got == [f"FROM Jeeves {SHOP} {NQ}"], 2.0), logs
    last = tmp_path / "run" / "last-from.txt"
    assert wait_until(lambda: last.is_file(), 2.0), logs
    assert "nothing queued" in last.read_text(encoding="utf-8")
    seat.close()


def test_seat_logs_held_nothing_queued_during_startup_grace(ircd, tmp_path):
    """During FR #955 grace, inject target is None; nothing-queued must be held AND logged."""
    seat = make_seat(ircd, machine="win-mpre8vi4u6u", pid=22836)
    logs: list[str] = []
    relay = bw.Relay(logs.append, persist_dir=tmp_path / "run")
    # no set_target -> held
    seat.on_message = relay.deliver
    seat.connect(timeout=5)
    ircd.send(f":Jeeves!j@h PRIVMSG {SHOP} :{NQ}")
    assert wait_until(lambda: any("held nothing-queued" in m for m in logs), 2.0)
    seat.close()
