"""FR #5525: PRIORITY prepare sends separate out + DONE PRIVMSGs (DONE detectors fire)."""
from __future__ import annotations

import re

import airc_console_service as svc
from airc_auth_helpers import ops_auth


def _service(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "test-only")
    args = svc.build_arg_parser().parse_args(
        ["--machine", "tm", "--home", str(tmp_path)]
    )
    service = svc.AircConsoleService(args)
    # FR #3639: live channel +o auth (operators list is ignored).
    service.core.auth = ops_auth("op", channel="#tm")
    service.core.channel = "#tm"
    sent: list[tuple[str, str]] = []
    service.send_privmsg = lambda nick, text, **kw: sent.append((nick, text))
    return service, sent


def test_fr5525_on_line_prepare_two_privmsgs(tmp_path, monkeypatch):
    service, sent = _service(tmp_path, monkeypatch)
    service.on_line(":op!u@h PRIVMSG tm_console :id=c25bd00e PRIORITY prepare")
    bodies = [t for nick, t in sent if nick == "op"]
    assert len(bodies) == 2, sent
    assert bodies[0].startswith("out id=c25bd00e seq=1 {")
    assert "PRIORITY prepare" not in bodies[0]
    assert "DONE" not in bodies[0]
    assert bodies[1] == "DONE id=c25bd00e exit=1"
    assert re.match(r"^DONE id=[0-9a-f]{8} exit=\d+$", bodies[1])


def test_fr5525_socket_bytes_two_crlf_privmsgs(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "test-only")
    monkeypatch.setattr(svc, "FLOOD_S", 0.0)
    args = svc.build_arg_parser().parse_args(
        ["--machine", "tm", "--home", str(tmp_path)]
    )
    service = svc.AircConsoleService(args)
    service.core.auth = ops_auth("op", channel="#tm")
    service.core.channel = "#tm"

    class _RecordingSock:
        def __init__(self) -> None:
            self.sent: list[bytes] = []

        def sendall(self, data: bytes) -> None:  # noqa: ANN001
            self.sent.append(data)

    sock = _RecordingSock()
    service.sock = sock
    service.on_line(":op!u@h PRIVMSG tm_console :id=c25bd00e PRIORITY prepare")
    raw = b"".join(sock.sent).decode("utf-8", errors="replace")
    frames = [p for p in raw.split("\r\n") if p.strip()]
    priv = [p for p in frames if p.upper().startswith("PRIVMSG OP :")]
    assert len(priv) == 2, frames
    b0 = priv[0].split(":", 1)[1]
    b1 = priv[1].split(":", 1)[1]
    assert b0.startswith("out id=c25bd00e seq=1 {")
    assert b1 == "DONE id=c25bd00e exit=1"
    assert re.match(r"^DONE id=[0-9a-f]{8} exit=\d+$", b1)
