"""FR #5826: CRED-SEAL same-length outbox scrub + CredHello preview masking."""
from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

import irc_agent


FAKE_TOKEN = "aabbccddeeff00112233445566778899"
FAKE_CT = "AAAA" + ("B" * 40)


def _seal_line(target: str = "flamingo_console") -> str:
    return (
        f"PRIVMSG {target} :id=c25bd00e CRED-SEAL "
        f"token={FAKE_TOKEN} seq=1/1 ct={FAKE_CT}"
    )


def _fake_ear_client(tmp_path: Path, *, chair: bool = False):
    class FakeArgs:
        pass

    args = FakeArgs()
    args.chair = chair
    client = object.__new__(irc_agent.Client)
    client.args = args
    client.sock = object()
    client.chan = "#flamingo"
    client.original_nick = "Bob-flamingo"
    client.home = tmp_path
    client._cred_seal_sweep_pending = True
    sent_wire: list[str] = []

    def fake_send_privmsg_lines(line):
        sent_wire.append(line)
        return [line]

    client.send_privmsg_lines = fake_send_privmsg_lines  # type: ignore[method-assign]
    client.say = lambda line: sent_wire.append(line)  # type: ignore[method-assign]
    client.send = lambda *_a, **_k: None  # type: ignore[method-assign]
    return client, sent_wire


def test_is_cred_seal_outbox_line_matches_privmsg_and_bare():
    assert irc_agent.is_cred_seal_outbox_line(_seal_line()) is True
    assert (
        irc_agent.is_cred_seal_outbox_line(
            f"id=c25bd00e CRED-SEAL token={FAKE_TOKEN} seq=1/1 ct={FAKE_CT}"
        )
        is True
    )
    assert irc_agent.is_cred_seal_outbox_line("PRIVMSG #flamingo :hello") is False
    assert irc_agent.is_cred_seal_outbox_line("CRED-HELLO token=x") is False


def test_scrub_cred_seal_preview_masks_token_and_ct():
    raw = _seal_line()
    scrubbed = irc_agent.scrub_cred_seal_preview(raw)
    assert FAKE_TOKEN not in scrubbed
    assert FAKE_CT not in scrubbed
    assert "token=***" in scrubbed
    assert "ct=***" in scrubbed


def test_take_outbox_records_preserves_spans_and_wrapper(tmp_path: Path):
    out = tmp_path / "outbox.txt"
    chat = "PRIVMSG #flamingo :hello\n"
    seal = _seal_line() + "\n"
    out.write_bytes(chat.encode("utf-8") + seal.encode("utf-8"))
    lines, new_last = irc_agent.take_outbox_lines(out, 0)
    records, new_last2 = irc_agent.take_outbox_records(out, 0)
    assert lines == [r[0] for r in records]
    assert new_last == new_last2 == out.stat().st_size
    assert records[1][1] == len(chat.encode("utf-8"))
    assert records[1][2] == out.stat().st_size
    assert records[1][3] == seal.encode("utf-8")


def test_drain_blanks_cred_seal_keeps_other_bytes(tmp_path: Path, monkeypatch):
    out = tmp_path / "outbox.txt"
    chat = "PRIVMSG #flamingo :hello shop\n"
    seal = _seal_line() + "\n"
    before = chat.encode("ascii") + seal.encode("ascii")
    out.write_bytes(before)
    client, sent = _fake_ear_client(tmp_path)
    logs: list[str] = []
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(irc_agent.bobreport, "chair_mode_active", lambda *_a, **_k: False)
    monkeypatch.setattr(irc_agent, "info", lambda msg: logs.append(str(msg)))

    got = client._drain_outbox_path(out)
    assert len(got) == 2
    assert sent[0].endswith(":hello shop")
    assert FAKE_TOKEN in sent[1]  # wire still carried the seal once
    after = out.read_bytes()
    assert len(after) == len(before)
    assert after.startswith(chat.encode("utf-8"))
    seal_region = after[len(chat.encode("utf-8")) :]
    assert seal_region.endswith(b"\n")
    assert FAKE_TOKEN.encode("utf-8") not in after
    assert FAKE_CT.encode("utf-8") not in after
    assert seal_region[:-1] == b" " * (len(seal) - 1)
    pos = int((tmp_path / "outbox.txt.pos").read_text(encoding="utf-8").strip())
    assert pos == len(after)
    # Previews must not leak ciphertext
    joined = "\n".join(logs)
    assert FAKE_TOKEN not in joined
    assert FAKE_CT not in joined


def test_drain_crlf_and_bom_preserve_length(tmp_path: Path, monkeypatch):
    out = tmp_path / "outbox.txt"
    seal = _seal_line() + "\r\n"
    payload = b"\xef\xbb\xbf" + seal.encode("utf-8")
    out.write_bytes(payload)
    client, _sent = _fake_ear_client(tmp_path)
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(irc_agent.bobreport, "chair_mode_active", lambda *_a, **_k: False)
    monkeypatch.setattr(irc_agent, "info", lambda *_a, **_k: None)
    client._drain_outbox_path(out)
    after = out.read_bytes()
    assert len(after) == len(payload)
    assert after.startswith(b"\xef\xbb\xbf")
    assert after.endswith(b"\r\n")
    assert FAKE_CT.encode("utf-8") not in after


def test_incomplete_tail_not_consumed(tmp_path: Path, monkeypatch):
    out = tmp_path / "outbox.txt"
    complete = b"PRIVMSG #flamingo :ok\n"
    incomplete = _seal_line().encode("ascii")  # no trailing newline
    out.write_bytes(complete + incomplete)
    client, sent = _fake_ear_client(tmp_path)
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(irc_agent.bobreport, "chair_mode_active", lambda *_a, **_k: False)
    monkeypatch.setattr(irc_agent, "info", lambda *_a, **_k: None)
    got = client._drain_outbox_path(out)
    assert got == ["PRIVMSG #flamingo :ok"]
    body = out.read_bytes()
    assert incomplete in body
    assert FAKE_TOKEN.encode("ascii") in body


def test_startup_sweep_blanks_legacy_prefix(tmp_path: Path, monkeypatch):
    out = tmp_path / "outbox.txt"
    seal = (_seal_line() + "\n").encode("ascii")
    chat = b"PRIVMSG #flamingo :later\n"
    out.write_bytes(seal + chat)
    # Pretend seal was already drained (pos past first line) but never scrubbed.
    irc_agent.save_outbox_pos(out, len(seal))
    client, sent = _fake_ear_client(tmp_path)
    client._cred_seal_sweep_pending = True
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(irc_agent.bobreport, "chair_mode_active", lambda *_a, **_k: False)
    monkeypatch.setattr(irc_agent, "info", lambda *_a, **_k: None)
    got = client._drain_outbox_path(out)
    assert got == ["PRIVMSG #flamingo :later"]
    body = out.read_bytes()
    assert FAKE_TOKEN.encode("utf-8") not in body
    assert FAKE_CT.encode("utf-8") not in body
    assert client._cred_seal_sweep_pending is False


def test_changed_span_skipped(tmp_path: Path, monkeypatch):
    out = tmp_path / "outbox.txt"
    seal = (_seal_line() + "\n").encode("ascii")
    out.write_bytes(seal)
    # Snapshot that will not match on-disk bytes
    bad_snap = b"X" * len(seal)
    blanked, failures = irc_agent.blank_cred_seal_spans(
        out, [(0, len(seal), bad_snap)], batch_end=len(seal)
    )
    assert blanked == 0
    assert failures == 1
    assert out.read_bytes() == seal


def test_send_oserror_still_scrubs(tmp_path: Path, monkeypatch):
    out = tmp_path / "outbox.txt"
    seal = (_seal_line() + "\n").encode("ascii")
    out.write_bytes(seal)
    client, _sent = _fake_ear_client(tmp_path)

    def boom(_line):
        raise OSError("send failed")

    client.send_privmsg_lines = boom  # type: ignore[method-assign]
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(irc_agent.bobreport, "chair_mode_active", lambda *_a, **_k: False)
    monkeypatch.setattr(irc_agent, "info", lambda *_a, **_k: None)
    client._drain_outbox_path(out)
    after = out.read_bytes()
    assert FAKE_TOKEN.encode("ascii") not in after
    assert len(after) == len(seal)
