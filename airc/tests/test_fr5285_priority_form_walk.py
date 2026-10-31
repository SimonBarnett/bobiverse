"""FR #5285: PRIORITY formStart / subform / getRows read path (fixture, no .mjs)."""
from __future__ import annotations

import json
from pathlib import Path

import airc_console as ac
import airc_priority as ap
from airc_auth_helpers import ops_auth
from repo_layout import ROOT

FIX = ROOT / "airc" / "priority-worker" / "fixtures" / "form_walk.json"


def _core(auth_ops=("bob-marchhare",), machine="marchhare", **kw):
    auth = ops_auth(*auth_ops, channel=f"#{machine}")
    return ac.AircConsoleCore(machine=machine, auth=auth, nick=f"{machine}_console", **kw)


def test_fr5285_parse_form_walk_verbs():
    p = ap.parse_priority_walk_command("PRIORITY formStart instance=fixture form=CUST")
    assert p is not None
    assert p[0] == "formStart"
    assert p[1]["instance"] == "fixture"
    assert p[1]["form"] == "CUST"
    p = ap.parse_priority_walk_command("id=aabbccdd PRIORITY getRows instance=fixture form=CUST")
    assert p is not None
    assert p[0] == "getRows"
    assert p[1]["id"] == "aabbccdd"
    assert ap.parse_priority_walk_command("UPDATE airc") is None
    assert ap.parse_priority_walk_command("PRIORITY prepare ENAME=FOO") is None


def test_fr5285_fixture_formstart_subform_getrows_no_mjs(tmp_path):
    allow = tmp_path / "priority-instances.json"
    allow.write_text(
        json.dumps(
            {
                "instances": [
                    {
                        "id": "fixture",
                        "url": "https://prioritydev.example.invalid",
                        "company": "live1",
                        "user": "api-user",
                        "credentialTarget": "PriorityWeb/fixture",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    core = _core(install_root=str(tmp_path), priority_allowlist=str(allow), priority_fixture=str(FIX))
    r1 = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :id=aabbccdd PRIORITY formStart instance=fixture form=CUST"
    )
    assert r1 is not None
    assert r1.action == "priority"
    lines = [ln for ln in (r1.reply or "").splitlines() if ln]
    assert any(ln.startswith("out id=aabbccdd seq=") for ln in lines)
    assert lines[-1] == "DONE id=aabbccdd exit=0"
    body = json.loads(lines[0].split(" ", 3)[-1])
    assert body["ok"] is True
    assert body["op"] == "formStart"
    assert body["form"] == "CUST"
    assert "password" not in json.dumps(body).lower()

    r2 = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :id=bbccddee PRIORITY subform instance=fixture form=CUST path=LINES"
    )
    assert r2 and "DONE id=bbccddee exit=0" in (r2.reply or "")
    b2 = json.loads([ln for ln in r2.reply.splitlines() if ln.startswith("out ")][0].split(" ", 3)[-1])
    assert b2["op"] == "subform"
    assert b2["path"] == "LINES"

    r3 = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :id=ccddeeff PRIORITY getRows instance=fixture form=CUST"
    )
    assert r3 and "DONE id=ccddeeff exit=0" in (r3.reply or "")
    b3 = json.loads([ln for ln in r3.reply.splitlines() if ln.startswith("out ")][0].split(" ", 3)[-1])
    assert b3["op"] == "getRows"
    assert isinstance(b3["rows"], list) and b3["rows"]


def test_fr5285_unknown_instance_and_password_refused(tmp_path):
    allow = tmp_path / "priority-instances.json"
    allow.write_text('{"instances":[{"id":"fixture","url":"https://prioritydev.example.invalid","company":"c","user":"u","credentialTarget":"t"}]}', encoding="utf-8")
    core = _core(install_root=str(tmp_path), priority_allowlist=str(allow), priority_fixture=str(FIX))
    r = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :id=deadbeef PRIORITY formStart instance=invented form=CUST"
    )
    assert r and r.action == "priority"
    assert "DONE id=deadbeef exit=2" in (r.reply or "")
    assert "unknown-instance" in (r.reply or "")

    r2 = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :PRIORITY formStart instance=fixture form=CUST password=secret"
    )
    assert r2 and r2.action == "priority"
    assert "exit=2" in (r2.reply or "")
    assert "password" not in (r2.reply or "").lower() or "password-refused" in (r2.reply or "")
    assert "secret" not in (r2.reply or "")


def test_fr5285_denied_unauthorized():
    core = _core()
    r = core.handle_raw(":evil!e@h PRIVMSG marchhare_console :PRIORITY formStart instance=fixture form=CUST")
    assert r and r.action == "deny"


def test_fr5285_allowed_when_shell_off(tmp_path):
    allow = tmp_path / "priority-instances.json"
    allow.write_text('{"instances":[{"id":"fixture","url":"https://prioritydev.example.invalid","company":"c","user":"u","credentialTarget":"t"}]}', encoding="utf-8")
    caps = ac.ConsoleCapabilities(shell_mode="off", jobs="off")
    core = _core(
        install_root=str(tmp_path),
        priority_allowlist=str(allow),
        priority_fixture=str(FIX),
        capabilities=caps,
    )
    r = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :id=11223344 PRIORITY getRows instance=fixture form=CUST"
    )
    assert r and r.action == "priority"
    assert "DONE id=11223344 exit=0" in (r.reply or "")


def test_fr5285_fixture_is_json_not_mjs():
    assert FIX.is_file()
    assert FIX.suffix == ".json"
    data = json.loads(FIX.read_text(encoding="utf-8"))
    assert "CUST" in data["forms"]
    worker = ROOT / "airc" / "scripts" / "airc_priority.py"
    assert worker.is_file()
    text = worker.read_text(encoding="utf-8")
    assert "formStart" in text
    assert "No agent .mjs" in text or "no agent" in text.lower()
    assert not worker.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "\u2014" not in text
