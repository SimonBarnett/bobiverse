"""FR #5742: action=bad_id must reach IRC via on_line (not only handle())."""
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
    logs: list[str] = []
    service.send_privmsg = lambda nick, text, **kw: sent.append((nick, text))
    monkeypatch.setattr(svc, "info", lambda msg: logs.append(str(msg)))
    return service, sent, logs


def test_fr5742_service_source_dispatches_bad_id():
    text = SVC.read_text(encoding="utf-8")
    assert '"bad_id"' in text or "'bad_id'" in text
    assert "FR #5742" in text or "bad_id" in text


def test_fr5742_on_line_sends_bad_id_err_and_done(tmp_path, monkeypatch):
    service, sent, logs = _service(tmp_path, monkeypatch)
    reply = ac.format_bad_id_reply("zz5678nx")
    service.core.handle_raw = lambda _line: ac.HandleResult(
        action="bad_id",
        nick="bob-mh",
        reply=reply,
        allow_mode="+o",
        allow_channel="#tm",
        allow_account="si",
    )
    service.on_line(":bob-mh!u@h PRIVMSG tm_console :id=zz5678nx ; New-Item x")
    assert ("bob-mh", "err id=zz5678nx seq=1 code=bad_id need-8-hex") in sent
    assert ("bob-mh", "DONE id=zz5678nx exit=2") in sent
    assert any("action=bad_id" in m for m in logs)
    # Must not echo the command body in the auth-allow line.
    assert not any("New-Item" in m for m in logs)


def test_fr5742_on_line_real_handle_nonhex_reaches_irc(tmp_path, monkeypatch):
    """End-to-end: real core.handle_raw bad_id + service dispatch."""
    from airc_auth_helpers import ops_auth

    service, sent, logs = _service(tmp_path, monkeypatch)
    auth = ops_auth("bob-mh", channel="#tm")
    service.core = ac.AircConsoleCore(
        machine="tm", auth=auth, nick="tm_console"
    )

    class _NoShell:
        def start(self, nick, command):
            raise AssertionError(f"shell must not start: {command!r}")

    service.core.shell_runner = _NoShell()
    service.on_line(
        ":bob-mh!u@h PRIVMSG tm_console :id=zz5678nx ; Write-Output leak"
    )
    bodies = [t for _, t in sent]
    assert any("code=bad_id" in t for t in bodies), bodies
    assert any(t.startswith("DONE id=") and "exit=2" in t for t in bodies), bodies
    assert not any("leak" in t.lower() for t in bodies)
