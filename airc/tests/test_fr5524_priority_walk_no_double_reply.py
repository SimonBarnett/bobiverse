"""FR #5524: PRIORITY walk sends out+DONE once (not _emit plus on_line)."""
from __future__ import annotations

import json
import airc_console as ac
import airc_console_service as svc
from airc_auth_helpers import ops_auth
from repo_layout import ROOT

FIX = ROOT / "airc" / "priority-worker" / "fixtures" / "form_walk.json"


def test_fr5524_walk_does_not_emit_and_reply(tmp_path):
    seen: list[tuple[str, str]] = []

    class StubJobs:
        def _emit(self, nick: str, line: str) -> None:
            seen.append((nick, line))

    allow = tmp_path / "priority-instances.json"
    allow.write_text(
        json.dumps(
            {
                "instances": [
                    {
                        "id": "fixture",
                        "url": "https://prioritydev.example.invalid",
                        "company": "c",
                        "user": "u",
                        "credentialTarget": "t",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    core = ac.AircConsoleCore(
        machine="marchhare",
        auth=ops_auth("bob-marchhare", channel="#marchhare"),
        nick="marchhare_console",
        install_root=str(tmp_path),
        priority_allowlist=str(allow),
        priority_fixture=str(FIX),
        job_protocol=StubJobs(),  # type: ignore[arg-type]
    )
    r = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :"
        "id=aabbccdd PRIORITY getRows instance=fixture form=CUST"
    )
    assert r and r.action == "priority"
    lines = [ln for ln in (r.reply or "").splitlines() if ln.strip()]
    assert sum(1 for ln in lines if ln.startswith("out id=aabbccdd")) == 1
    assert sum(1 for ln in lines if ln.startswith("DONE id=aabbccdd")) == 1
    assert seen == []


def test_fr5524_on_line_sends_walk_once(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "test-only")
    args = svc.build_arg_parser().parse_args(["--machine", "tm", "--home", str(tmp_path)])
    service = svc.AircConsoleService(args)
    sent: list[str] = []
    service.send_privmsg = lambda nick, text, **kw: sent.append(text)
    service.core.handle_raw = lambda _line: ac.HandleResult(
        action="priority",
        nick="op",
        reply="out id=b780ec0f seq=1 {\"ok\":false,\"error\":\"unknown-instance\"}\nDONE id=b780ec0f exit=2",
    )
    service.on_line(":op!u@h PRIVMSG tm_console :id=b780ec0f PRIORITY getRows instance=x form=CUST")
    outs = [t for t in sent if t.startswith("out id=b780ec0f")]
    dones = [t for t in sent if t.startswith("DONE id=b780ec0f")]
    assert len(outs) == 1
    assert len(dones) == 1


def test_fr5524_pins():
    src = (ROOT / "airc" / "scripts" / "airc_console.py").read_text(encoding="utf-8")
    assert "FR #5524" in src
    walk = src.split("parse_priority_walk_command")[1].split("parse_priority_command")[0]
    assert "job_protocol._emit" not in walk
    assert not (ROOT / "airc" / "scripts" / "airc_console.py").read_bytes().startswith(b"\xef\xbb\xbf")
