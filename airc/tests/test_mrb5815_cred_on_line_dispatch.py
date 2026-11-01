"""MRB #5815: CRED HELLO/SEAL replies must reach IRC."""
from __future__ import annotations

import airc_console as ac
import airc_console_service as svc


def test_mrb5815_on_line_sends_cred_hello_and_seal_replies(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "test-only")
    args = svc.build_arg_parser().parse_args(["--machine", "tm", "--home", str(tmp_path)])
    service = svc.AircConsoleService(args)
    sent: list[tuple[str, str]] = []
    service.send_privmsg = lambda nick, text, **kw: sent.append((nick, text))

    for reply in (
        "CRED-HELLO token=fixture pub=fixture exp=soon alg=x25519-chacha20poly1305",
        "cred-persisted target=fixture account=fixture\n"
        "DONE id=aabbccdd exit=0 cred-persisted",
    ):
        sent.clear()
        service.core.handle_raw = lambda _line, value=reply: ac.HandleResult(
            action="cred",
            nick="operator",
            reply=value,
        )
        service.on_line(":operator!u@h PRIVMSG tm_console :id=aabbccdd CRED persist")
        expected = [line for line in reply.splitlines() if line.strip()]
        assert [text for nick, text in sent if nick == "operator"] == expected
