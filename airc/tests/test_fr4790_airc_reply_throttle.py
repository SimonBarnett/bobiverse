"""FR #4790: airc console reply throttle / truncate for large bursts.

Foundation (this FR):
- Cap IRC out/err reply lines per shell job; emit truncate marker + DONE.
- Token-bucket flood pacing under Ergo fakelag (replace fixed sleep-only).
- Document: large binary transfers must not dump base64 over PRIVMSG.

Child FRs (filed separately): resumable continuation, file-fetch GET/upload,
controller command pacing.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

import airc_console as ac
import airc_console_service as svc


def test_fr4790_constants_and_helpers_exist():
    assert hasattr(ac, "SHELL_REPLY_MAX_IRC_LINES")
    assert int(ac.SHELL_REPLY_MAX_IRC_LINES) >= 16
    assert int(ac.SHELL_REPLY_MAX_IRC_LINES) <= 128
    assert hasattr(svc, "FloodTokenBucket")
    assert hasattr(svc, "FLOOD_RATE_PER_S")
    assert float(svc.FLOOD_RATE_PER_S) > 0
    assert float(svc.FLOOD_RATE_PER_S) <= 3.0


def test_fr4790_format_shell_replies_truncates_with_marker():
    """Hundreds of base64 lines must not all become PRIVMSG replies."""
    # ~200 IRC-sized lines of payload (incident class: xlsx base64 dump).
    lines = [f"LINE{i:04d}-" + ("B" * 280) for i in range(200)]
    stdout = "\n".join(lines)
    out = ac.ShellOutcome(job_id="aabbccdd", exit_code=0, stdout=stdout, stderr="")
    records = ac.format_shell_replies(out, irc_limit=ac.IRC_SAFE_PAYLOAD)
    assert records[-1] == "DONE id=aabbccdd exit=0"
    body_lines = [r for r in records if r.startswith("out ") or r.startswith("err ")]
    assert len(body_lines) <= ac.SHELL_REPLY_MAX_IRC_LINES + 2  # + truncate err
    joined = "\n".join(records)
    assert "output truncated" in joined.lower()
    assert "FR #4790" in joined or "fr #4790" in joined.lower()
    # Must still include early content
    assert any("LINE0000" in r for r in records)


def test_fr4790_small_output_not_truncated():
    out = ac.ShellOutcome(
        job_id="deadbeef",
        exit_code=0,
        stdout="hello\nworld",
        stderr="",
    )
    records = ac.format_shell_replies(out)
    assert records[-1] == "DONE id=deadbeef exit=0"
    assert "output truncated" not in "\n".join(records).lower()
    assert any("hello" in r for r in records)
    assert any("world" in r for r in records)


def test_fr4790_token_bucket_paces_under_burst():
    bucket = svc.FloodTokenBucket(rate=2.0, capacity=2.0)
    waits = []
    for _ in range(6):
        waits.append(bucket.take(1.0))
    # First capacity tokens free; later calls must wait.
    assert waits[0] == 0.0
    assert waits[1] == 0.0
    assert any(w > 0.05 for w in waits[2:])


def test_fr4790_service_send_uses_token_bucket(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "x-server-pass")
    args = svc.build_arg_parser().parse_args(
        ["--machine", "tm", "--home", str(tmp_path), "--shop-mode", "registered", "--operators", "op"]
    )
    s = svc.AircConsoleService(args)
    assert isinstance(s._flood_bucket, svc.FloodTokenBucket)
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda sec: sleeps.append(float(sec)))
    # Fake socket sendall
    class _Sock:
        def sendall(self, _data: bytes) -> None:
            return None

    s.sock = _Sock()  # type: ignore[assignment]
    # Drain capacity then force waits
    for _ in range(12):
        s.send("PING :x", flood=True)
    assert any(x > 0.05 for x in sleeps), f"expected token-bucket waits, got {sleeps!r}"


def test_fr4790_docs_mention_truncate_and_no_base64_dump():
    root = Path(__file__).resolve().parents[1]
    docs = [
        root / "docs" / "airc-remote-control.md",
        root / ".grok" / "skills" / "bobiverse-airc-troubleshooting" / "SKILL.md",
    ]
    blob = "\n".join(p.read_text(encoding="utf-8") for p in docs if p.is_file())
    assert "FR #4790" in blob or "4790" in blob
    assert "output truncated" in blob.lower() or "SHELL_REPLY_MAX" in blob
    assert "base64" in blob.lower()
