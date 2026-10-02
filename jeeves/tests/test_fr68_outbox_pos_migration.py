"""FR #68: migrate chair-outbox cursor; do not replay backlog or starve +o / ChanServ."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import bob_home  # noqa: E402
import irc_agent  # noqa: E402


def test_migration_seals_chair_outbox_at_eof_when_pos_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(bob_home, "_profile", lambda: tmp_path / "me")
    monkeypatch.setattr(bob_home, "_admin_profile", lambda: tmp_path / "Administrator")
    old = tmp_path / ".agentic-irc-bobiverse"
    old.mkdir()
    body = b"PRIVMSG #bobiverse :GIT old-1\nPRIVMSG #bobiverse :GIT old-2\n"
    (old / "chair-outbox.txt").write_bytes(body)
    (old / "digest.json").write_text("{}", encoding="utf-8")
    # .pos intentionally absent in legacy (or skipped historically)
    new = tmp_path / ".bobiverse"
    res = bob_home.migrate_legacy(new)
    assert res["status"] == "migrated"
    out = new / "chair-outbox.txt"
    pos = new / "chair-outbox.txt.pos"
    assert out.is_file()
    assert pos.is_file(), "missing pos must be sealed so drain does not replay backlog"
    assert int(pos.read_text(encoding="utf-8").strip()) == out.stat().st_size
    assert "chair-outbox.txt.pos" in res.get("outbox_pos_sealed", [])


def test_migration_copies_existing_outbox_pos_when_present(tmp_path, monkeypatch):
    monkeypatch.setattr(bob_home, "_profile", lambda: tmp_path / "me")
    monkeypatch.setattr(bob_home, "_admin_profile", lambda: tmp_path / "Administrator")
    old = tmp_path / ".agentic-irc-bobiverse"
    old.mkdir()
    body = b"PRIVMSG #bobiverse :GIT a\nPRIVMSG #bobiverse :GIT b\n"
    (old / "chair-outbox.txt").write_bytes(body)
    (old / "chair-outbox.txt.pos").write_text("42\n", encoding="utf-8")
    (old / "digest.json").write_text("{}", encoding="utf-8")
    new = tmp_path / ".bobiverse"
    res = bob_home.migrate_legacy(new)
    assert res["status"] == "migrated"
    assert (new / "chair-outbox.txt.pos").read_text(encoding="utf-8").strip() == "42"
    assert "chair-outbox.txt.pos" in res.get("outbox_pos_sealed", [])


def test_migration_accepts_legacy_chair_outbox_pos_name(tmp_path, monkeypatch):
    """Some installs used chair-outbox.pos next to chair-outbox.txt."""
    monkeypatch.setattr(bob_home, "_profile", lambda: tmp_path / "me")
    monkeypatch.setattr(bob_home, "_admin_profile", lambda: tmp_path / "Administrator")
    old = tmp_path / ".agentic-irc-bobiverse"
    old.mkdir()
    (old / "chair-outbox.txt").write_bytes(b"PRIVMSG #bobiverse :x\n")
    (old / "chair-outbox.pos").write_text("7\n", encoding="utf-8")
    (old / "digest.json").write_text("{}", encoding="utf-8")
    new = tmp_path / ".bobiverse"
    bob_home.migrate_legacy(new)
    assert (new / "chair-outbox.txt.pos").read_text(encoding="utf-8").strip() == "7"


def test_take_outbox_lines_respects_max_lines(tmp_path):
    p = tmp_path / "chair-outbox.txt"
    p.write_text(
        "PRIVMSG #bobiverse :one\nPRIVMSG #bobiverse :two\nPRIVMSG #bobiverse :three\n",
        encoding="utf-8",
    )
    lines, pos = irc_agent.take_outbox_lines(p, 0, max_lines=2)
    assert lines == ["PRIVMSG #bobiverse :one", "PRIVMSG #bobiverse :two"]
    # pos stops after line 2 so a later tick can continue
    more, pos2 = irc_agent.take_outbox_lines(p, pos, max_lines=2)
    assert more == ["PRIVMSG #bobiverse :three"]
    assert pos2 == p.stat().st_size


def test_drain_outbox_path_caps_lines_per_tick(tmp_path, monkeypatch):
    out = tmp_path / "outbox.txt"
    lines = [f"PRIVMSG #x :{i}" for i in range(20)]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    class FakeArgs:
        chair = False

    client = object.__new__(irc_agent.Client)
    client.args = FakeArgs()
    client.sock = object()  # truthy
    client.chan = "#x"
    client.original_nick = "Jeeves"
    client.home = tmp_path
    sent_wire: list[str] = []

    def fake_send_privmsg_lines(line):
        sent_wire.append(line)
        return [line]

    client.send_privmsg_lines = fake_send_privmsg_lines  # type: ignore[method-assign]
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(irc_agent.bobreport, "chair_mode_active", lambda *_a, **_k: False)

    first = client._drain_outbox_path(out)
    assert len(first) == irc_agent.OUTBOX_LINES_PER_TICK
    assert len(sent_wire) == irc_agent.OUTBOX_LINES_PER_TICK
    pos = int((tmp_path / "outbox.txt.pos").read_text(encoding="utf-8").strip())
    assert 0 < pos < out.stat().st_size

    second = client._drain_outbox_path(out)
    assert len(second) == irc_agent.OUTBOX_LINES_PER_TICK
    assert len(sent_wire) == 2 * irc_agent.OUTBOX_LINES_PER_TICK


def test_outbox_loop_runs_chan_ops_before_drain_for_chair(tmp_path, monkeypatch):
    order: list[str] = []

    class FakeArgs:
        chair = True

    client = object.__new__(irc_agent.Client)
    client.args = FakeArgs()
    client.stop = mock.Mock()
    client.stop.is_set.side_effect = [False, True]
    client.dead = mock.Mock()
    client.dead.is_set.return_value = False
    client.joined = mock.Mock()
    client.joined.wait.return_value = True
    client._outbox_gen = 1

    def mark(name):
        def _(*_a, **_k):
            order.append(name)

        return _

    client.drain_outbox_once = mark("drain")  # type: ignore[method-assign]
    client._maybe_bobiverse_pull = mark("pull")  # type: ignore[method-assign]
    client._maybe_chanserv_sync = mark("chanserv")  # type: ignore[method-assign]
    client._ensure_chan_ops = mark("ops")  # type: ignore[method-assign]
    client._chan_privs_tick = mark("privs")  # type: ignore[method-assign]
    client._maybe_depart_request = mark("depart")  # type: ignore[method-assign]
    client._maybe_prune_talk_seat_ghosts = mark("prune")  # type: ignore[method-assign]
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)

    client.outbox_loop(gen=1)
    assert order.index("ops") < order.index("drain")
    assert order.index("chanserv") < order.index("drain")
