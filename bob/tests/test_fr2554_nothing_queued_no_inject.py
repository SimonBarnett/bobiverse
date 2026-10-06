"""FR #2554 / supersedes inject-to-agent part of FR #994.

CAST IRON: Jeeves ``<nick>: nothing queued`` must NOT be injected into the agent session
(only real assigns may wake the model). Operators still get an explicit skip log and
optional last-from.txt audit.
"""
from __future__ import annotations

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


def test_relay_skips_nothing_queued_not_injected(tmp_path):
    logs: list[str] = []
    inj: list[str] = []
    r = bw.Relay(logs.append, persist_dir=tmp_path)
    r.set_target(lambda line: inj.append(line) or True)
    assert r.deliver("Jeeves", SHOP, NQ) == "skipped"
    assert inj == []
    assert any("skipped nothing-queued" in m and "not injected" in m for m in logs)
    last = tmp_path / "last-from.txt"
    assert last.is_file()
    assert "nothing queued" in last.read_text(encoding="utf-8")


def test_relay_still_injects_real_assign(tmp_path):
    logs: list[str] = []
    inj: list[str] = []
    r = bw.Relay(logs.append, persist_dir=tmp_path)
    r.set_target(lambda line: inj.append(line) or True)
    body = f"{NICK}: FR SimonBarnett/bobiverse#2554 https://github.com/SimonBarnett/bobiverse/issues/2554"
    assert r.deliver("Jeeves", SHOP, body) == "injected"
    assert len(inj) == 1
    assert "FR SimonBarnett/bobiverse#2554" in inj[0]
    assert any(m.startswith("relay: injected ") for m in logs)


def test_pending_flush_skips_nothing_queued(tmp_path):
    logs: list[str] = []
    inj: list[str] = []
    r = bw.Relay(logs.append, persist_dir=tmp_path)
    # hold while no target
    assert r.deliver("Jeeves", SHOP, NQ) == "skipped"  # skip even when held would have applied
    # Also simulate a FROM line already pending (pre-#2554 hold path)
    r._pending.append(f"FROM Jeeves {SHOP} {NQ}")
    r.set_target(lambda line: inj.append(line) or True)
    assert inj == []
    assert any("pending flush" in m for m in logs)


def test_seat_does_not_inject_jeeves_nothing_queued(ircd, tmp_path):
    # FR #2806 / t817u: nothing-queued is inbound_kind nak — handled on the seat before on_message,
    # so Relay never sees it (Relay unit tests above still cover deliver-time skip + last-from).
    seat = make_seat(ircd, machine="win-mpre8vi4u6u", pid=22836)
    assert seat.nick == NICK
    got: list[str] = []
    logs: list[str] = []
    nakked: list[int] = []
    seat.log = logs.append
    seat.on_nak = lambda: nakked.append(1)
    relay = bw.Relay(lambda _m: None, persist_dir=tmp_path / "run")
    relay.set_target(lambda line: got.append(line) or True)
    seat.on_message = relay.deliver
    seat.connect(timeout=5)
    ircd.send(f":Jeeves!j@h PRIVMSG {SHOP} :{NQ}")
    assert wait_until(
        lambda: any("nothing queued" in m and "not relayed" in m for m in logs), 2.0
    ), logs
    assert got == []
    assert nakked, "FR #2806: nothing queued must arm on_nak / BoredEmitter.nak_s"
    assert bw.inbound_kind(NQ, NICK) == "nak"
    seat.close()
