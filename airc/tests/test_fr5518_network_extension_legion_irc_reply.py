"""FR #5518: NETWORK / EXTENSION / LEGION accepted+DONE must go out on IRC."""
from __future__ import annotations

from pathlib import Path

import airc_console as ac
import airc_console_service as svc
from repo_layout import ROOT

SVC = ROOT / "airc" / "scripts" / "airc_console_service.py"


def _service(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "test-only")
    args = svc.build_arg_parser().parse_args(["--machine", "tm", "--home", str(tmp_path)])
    service = svc.AircConsoleService(args)
    sent: list[tuple[str, str]] = []
    service.send_privmsg = lambda nick, text, **kw: sent.append((nick, text))
    return service, sent


def test_fr5518_service_reply_set_includes_network_family():
    text = SVC.read_text(encoding="utf-8")
    assert "network" in text and "extension" in text and "legion" in text
    assert "FR #5518" in text


def test_fr5518_on_line_sends_network_accepted_done(tmp_path, monkeypatch):
    service, sent = _service(tmp_path, monkeypatch)
    service.core.handle_raw = lambda _line: ac.HandleResult(
        action="network",
        nick="bob-mh",
        reply="NETWORK accepted id=aabbccdd action=diag\nDONE id=aabbccdd exit=0",
        allow_mode="+o",
        allow_channel="#tm",
    )
    service.on_line(":bob-mh!u@h PRIVMSG tm_console :id=aabbccdd NETWORK diag")
    assert ("bob-mh", "NETWORK accepted id=aabbccdd action=diag") in sent
    assert ("bob-mh", "DONE id=aabbccdd exit=0") in sent


def test_fr5518_on_line_sends_extension_and_legion(tmp_path, monkeypatch):
    service, sent = _service(tmp_path, monkeypatch)
    for action, reply in (
        ("extension", "EXTENSION accepted id=11223344\nDONE id=11223344 exit=0"),
        ("legion", "LEGION accepted id=55667788 target=flamingo\nDONE id=55667788 exit=0"),
    ):
        sent.clear()
        service.core.handle_raw = lambda _line, a=action, r=reply: ac.HandleResult(
            action=a, nick="op", reply=r
        )
        service.on_line(":op!u@h PRIVMSG tm_console :probe")
        assert any("accepted" in t for _, t in sent), (action, sent)
        assert any(t.startswith("DONE id=") for _, t in sent), (action, sent)
