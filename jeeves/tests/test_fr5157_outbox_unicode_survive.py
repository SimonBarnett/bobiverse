"""FR #5157: Jeeves outbox thread must survive UnicodeEncodeError (same as #4396/#4397)."""
from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "common" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import irc_agent  # noqa: E402
import jeeves_main  # noqa: E402

SKILL = ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-troubleshooting" / "SKILL.md"


def test_fr5157_cp1252_rejects_arrow():
    with pytest.raises(UnicodeEncodeError):
        "\u2192".encode("cp1252")


def test_fr5157_info_survives_cp1252_stdout(monkeypatch):
    buf = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", buf)
    irc_agent.info("INFO outbox: sent PRIVMSG #x :A \u2192 B")
    buf.flush()
    text = buf.buffer.getvalue().decode("cp1252", errors="replace")
    assert "INFO outbox: sent" in text


def test_fr5157_outbox_loop_survives_unicode_and_keeps_running(monkeypatch):
    ticks = {"n": 0}

    class FakeArgs:
        chair = True

    client = object.__new__(irc_agent.Client)
    client.args = FakeArgs()
    client.stop = mock.Mock()
    client.stop.is_set.side_effect = [False, False, True]
    client.dead = mock.Mock()
    client.dead.is_set.return_value = False
    client.joined = mock.Mock()
    client.joined.wait.return_value = True
    client._outbox_gen = 1

    def boom_then_ok(*_a, **_k):
        ticks["n"] += 1
        if ticks["n"] == 1:
            raise UnicodeEncodeError("cp1252", "\u2192", 0, 1, "ordinal not in range")

    client._maybe_bobiverse_pull = lambda: None
    client._maybe_chanserv_sync = lambda: None
    client._ensure_chan_ops = lambda: None
    client._chan_privs_tick = lambda: None
    client.drain_outbox_once = boom_then_ok
    client._chair_jobs_tick = lambda: None
    client._maybe_depart_request = lambda: None
    client._maybe_prune_talk_seat_ghosts = lambda: None
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    logs: list[str] = []
    monkeypatch.setattr(irc_agent, "info", logs.append)

    client.outbox_loop(gen=1)
    assert ticks["n"] >= 2
    assert any("ERROR outbox-loop" in x and "UnicodeEncodeError" in x for x in logs)


def test_fr5157_drain_skips_one_bad_line_and_sends_next(tmp_path, monkeypatch):
    out = tmp_path / "outbox.txt"
    out.write_text(
        "PRIVMSG #x :good1\nPRIVMSG #x :arrow \u2192 here\nPRIVMSG #x :good2\n",
        encoding="utf-8",
    )

    class FakeArgs:
        chair = False

    client = object.__new__(irc_agent.Client)
    client.args = FakeArgs()
    client.sock = object()
    client.chan = "#x"
    client.original_nick = "Jeeves"
    client.home = tmp_path
    sent: list[str] = []

    def fake_send(line):
        if "\u2192" in line:
            raise UnicodeEncodeError("cp1252", "\u2192", 0, 1, "ordinal not in range")
        sent.append(line)
        return [line]

    client.send_privmsg_lines = fake_send
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(irc_agent.bobreport, "chair_mode_active", lambda *_a, **_k: False)
    logs: list[str] = []
    monkeypatch.setattr(irc_agent, "info", logs.append)

    wire = client._drain_outbox_path(out)
    assert any("good1" in w for w in wire)
    assert any("good2" in w for w in wire)
    assert not any("\u2192" in w for w in wire)
    assert any("ERROR outbox" in x for x in logs)


def test_fr5157_jeeves_main_safe_print_cp1252(monkeypatch):
    buf = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", buf)
    jeeves_main.safe_print("FINDING A \u2192 B")
    buf.flush()
    text = buf.buffer.getvalue().decode("cp1252", errors="replace")
    assert "FINDING A" in text


def test_fr5157_skill_row():
    text = SKILL.read_text(encoding="utf-8")
    assert "5157" in text
    assert "UnicodeEncodeError" in text
    assert "outbox" in text.lower()
