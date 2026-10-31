"""MRB #5337 hostile pins for PRIORITY form walk (FR #5285)."""
from __future__ import annotations

import json
from pathlib import Path

import airc_console as ac
import airc_priority as ap
from airc_auth_helpers import ops_auth
from repo_layout import ROOT

FIX = ROOT / "airc" / "priority-worker" / "fixtures" / "form_walk.json"


def _allow(tmp_path: Path) -> Path:
    p = tmp_path / "priority-instances.json"
    p.write_text(
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
    return p


def test_mrb5337_job_protocol_emit_delivers_out_and_done(tmp_path):
    """Live service path uses JobProtocol._emit for form-walk lines."""
    seen: list[tuple[str, str]] = []

    class StubJobs:
        def _emit(self, nick: str, line: str) -> None:
            seen.append((nick, line))

    allow = _allow(tmp_path)
    auth = ops_auth("bob-marchhare", channel="#marchhare")
    core = ac.AircConsoleCore(
        machine="marchhare",
        auth=auth,
        nick="marchhare_console",
        install_root=str(tmp_path),
        priority_allowlist=str(allow),
        priority_fixture=str(FIX),
        job_protocol=StubJobs(),  # type: ignore[arg-type]
    )
    r = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :"
        "id=aabbccdd PRIORITY formStart instance=fixture form=CUST"
    )
    assert r and r.action == "priority"
    assert seen, "expected JobProtocol._emit calls for live IRC delivery"
    assert seen[0][0] == "bob-marchhare"
    assert any(ln.startswith("out id=aabbccdd") for _, ln in seen)
    assert any(ln == "DONE id=aabbccdd exit=0" for _, ln in seen)


def test_mrb5337_refuse_url_kv_does_not_bypass_allowlist(tmp_path):
    allow = _allow(tmp_path)
    auth = ops_auth("bob-marchhare", channel="#marchhare")
    core = ac.AircConsoleCore(
        machine="marchhare",
        auth=auth,
        nick="marchhare_console",
        install_root=str(tmp_path),
        priority_allowlist=str(allow),
        priority_fixture=str(FIX),
    )
    r = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :"
        "PRIORITY formStart instance=nope form=CUST url=https://evil.example"
    )
    assert r and r.action == "priority"
    assert "unknown-instance" in (r.reply or "")
    assert "exit=2" in (r.reply or "")


def test_mrb5337_docs_and_fixture_have_no_secrets():
    remote = (ROOT / "airc/docs/airc-remote-control.md").read_text(encoding="utf-8")
    assert "formStart" in remote
    fix = FIX.read_text(encoding="utf-8")
    assert "password" not in fix.lower()
    assert "CUST" in fix


def test_mrb5337_walk_parser_separate_from_connect():
    assert ap.parse_priority_walk_command("PRIORITY connect fixture") is None
    assert ap.parse_priority_command("PRIORITY formStart instance=fixture form=CUST") is None
    assert ap.parse_priority_walk_command("PRIORITY formStart instance=fixture form=CUST") is not None
