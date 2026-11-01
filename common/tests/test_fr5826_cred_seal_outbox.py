"""FR #5826: scrub consumed CRED-SEAL ciphertext from the ear outbox."""
from __future__ import annotations

from pathlib import Path

import pytest

import irc_agent


TOKEN = "0123456789abcdef0123456789abcdef"
CIPHERTEXT = "not-real-ciphertext"
CRED_LINE = (
    "PRIVMSG tm_console :id=c5826001 CRED-SEAL "
    f"token={TOKEN} seq=1/1 ct={CIPHERTEXT}"
)
SAFE_LINE = "PRIVMSG #marchhare :ordinary ear line"


@pytest.mark.parametrize("send_error", [False, True])
def test_consumed_cred_seal_is_scrubbed_without_offset_or_log_leak(
    tmp_path: Path, monkeypatch, send_error: bool
):
    outbox = tmp_path / "outbox.txt"
    outbox.write_text(f"{CRED_LINE}\n{SAFE_LINE}\n", encoding="utf-8")
    original_size = outbox.stat().st_size

    class Args:
        chair = False

    client = object.__new__(irc_agent.Client)
    client.args = Args()
    client.sock = object()
    client.chan = "#marchhare"
    client.original_nick = "Bob-marchhare"
    client.home = tmp_path
    sent: list[str] = []
    logs: list[str] = []

    def send_privmsg(line: str) -> list[str]:
        if send_error and line == CRED_LINE:
            raise OSError("transient")
        sent.append(line)
        return [line]

    client.send_privmsg_lines = send_privmsg  # type: ignore[method-assign]
    client.say = lambda _line: None
    client.send = lambda *_a, **_k: None
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a: None)
    monkeypatch.setattr(irc_agent.bobreport, "chair_mode_active", lambda *_a: False)
    monkeypatch.setattr(irc_agent, "info", logs.append)

    drained = client._drain_outbox_path(outbox)

    assert drained == ([SAFE_LINE] if send_error else [CRED_LINE, SAFE_LINE])
    assert sent == drained
    content = outbox.read_text(encoding="utf-8")
    assert "CRED-SEAL" not in content
    assert TOKEN not in content
    assert CIPHERTEXT not in content
    assert SAFE_LINE in content
    assert outbox.stat().st_size == original_size
    assert irc_agent.load_outbox_pos(outbox) == original_size
    assert all(TOKEN not in line and CIPHERTEXT not in line for line in logs)
