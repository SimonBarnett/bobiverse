"""FR #5284 / #5275: PRIORITY connect/status + allowlist/CredMan schema."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import airc_console as ac
import airc_priority as ap
from airc_auth_helpers import ops_auth
from repo_layout import ROOT

EXAMPLE = ROOT / "airc/config/priority-instances.example.json"


def _core(**kw):
    auth = ops_auth("bob-marchhare", channel="#marchhare")
    return ac.AircConsoleCore(machine="marchhare", auth=auth, nick="marchhare_console", **kw)


def _allowlist(tmp_path: Path, rows: list[dict] | None = None) -> Path:
    doc = {
        "instances": rows
        or [
            {
                "id": "dev1",
                "url": "https://prioritydev.example.invalid",
                "company": "live1",
                "user": "api-user",
                "credentialTarget": "PriorityWeb/dev1",
            }
        ]
    }
    p = tmp_path / "priority-instances.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def test_fr5275_example_allowlist_loads_and_rejects_password_key(tmp_path):
    al = ap.load_priority_allowlist(EXAMPLE)
    assert "example-dev" in al
    inst = al["example-dev"]
    assert inst.url.startswith("https://")
    assert inst.credential_target
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "instances": [
                    {
                        "id": "x",
                        "url": "https://x.example",
                        "company": "c",
                        "user": "u",
                        "credentialTarget": "t",
                        "password": "nope",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ap.PriorityConfigError, match="password"):
        ap.load_priority_allowlist(bad)


def test_fr5275_empty_and_unknown_instance_fail_closed(tmp_path):
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"instances": []}), encoding="utf-8")
    with pytest.raises(ap.PriorityConfigError, match="empty"):
        ap.load_priority_allowlist(empty)
    al = ap.load_priority_allowlist(_allowlist(tmp_path))
    with pytest.raises(ap.PriorityConfigError, match="unknown"):
        ap.get_instance("no-such", al)
    http_dir = tmp_path / "http"
    http_dir.mkdir()
    with pytest.raises(ap.PriorityConfigError, match="https"):
        ap.load_priority_allowlist(
            _allowlist(
                http_dir,
                [
                    {
                        "id": "x",
                        "url": "http://insecure.example",
                        "company": "c",
                        "user": "u",
                        "credentialTarget": "t",
                    }
                ],
            )
        )


def test_fr5284_parse_priority_command_shapes():
    assert ap.parse_priority_command("PRIORITY connect dev1") == (None, "connect", "dev1")
    assert ap.parse_priority_command("priority status") == (None, "status", None)
    assert ap.parse_priority_command("id=aabbccdd PRIORITY status dev1") == (
        "aabbccdd",
        "status",
        "dev1",
    )
    assert ap.parse_priority_command("UPDATE airc") is None
    assert ap.parse_priority_command("PRIORITY prepare x") is None


def test_fr5284_connect_mock_happy_path_no_password_on_wire(tmp_path):
    path = _allowlist(tmp_path)
    seen: dict[str, str] = {}

    def cred(target: str) -> str:
        seen["target"] = target
        return "FAKE_PRIORITY_PASSWORD_FOR_TEST"

    r = ap.run_priority_verb(
        "connect",
        "dev1",
        job_id="aabbccdd",
        allowlist_path=path,
        cred_fetcher=cred,
        connector=ap.mock_connect,
    )
    assert r.ok and r.exit_code == 0
    assert seen["target"] == "PriorityWeb/dev1"
    text = r.reply_text()
    assert "out id=aabbccdd seq=1" in text
    assert "DONE id=aabbccdd exit=0" in text
    assert "FAKE_PRIORITY_PASSWORD_FOR_TEST" not in text
    assert "password" not in text.lower()
    payload = json.loads(text.split("seq=1 ", 1)[1].split("\n", 1)[0])
    assert payload["ok"] is True
    assert payload["company"] == "live1"
    assert payload["url"].startswith("https://")


def test_fr5284_status_list_and_unknown_id(tmp_path):
    path = _allowlist(tmp_path)
    r = ap.run_priority_verb("status", None, job_id="11111111", allowlist_path=path)
    assert r.ok
    assert r.payload["instances"] == ["dev1"]
    r2 = ap.run_priority_verb("connect", "missing", job_id="22222222", allowlist_path=path)
    assert not r2.ok
    assert "unknown instance" in r2.error.lower()
    assert "DONE id=22222222 exit=1" in r2.reply_text()


def test_fr5284_wire_authorized_connect_and_deny(tmp_path):
    path = _allowlist(tmp_path)

    def runner(subcmd, instance_id, **kwargs):
        return ap.run_priority_verb(
            subcmd,
            instance_id,
            job_id=kwargs.get("job_id"),
            allowlist_path=path,
            cred_fetcher=lambda _t: "FAKE_PW",
            connector=ap.mock_connect,
        )

    core = _core(priority_runner=runner, priority_allowlist_path=str(path))
    r = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :id=abcd1234 PRIORITY connect dev1"
    )
    assert r and r.action == "priority"
    assert r.reply
    assert "DONE id=abcd1234 exit=0" in r.reply
    assert "FAKE_PW" not in r.reply
    assert "password" not in r.reply.lower()

    denied = core.handle_raw(":evil!e@h PRIVMSG marchhare_console :PRIORITY connect dev1")
    assert denied and denied.action == "deny"
    assert "DONE" in (denied.reply or "") and "126" in (denied.reply or "")


def test_fr5284_help_mentions_priority():
    core = _core()
    r = core.handle_raw(":bob-marchhare!u@h PRIVMSG marchhare_console :.help")
    assert r and r.action == "help"
    assert "PRIORITY" in (r.reply or "")


def test_fr5284_docs_point_at_allowlist_and_verbs():
    remote = (ROOT / "airc/docs/airc-remote-control.md").read_text(encoding="utf-8")
    assert "PRIORITY connect" in remote
    assert "CredMan" in remote
    schema = ROOT / "airc/docs/airc-priority-client.md"
    assert schema.is_file()
    body = schema.read_text(encoding="utf-8")
    assert "priority-instances" in body
    assert "PRIORITY connect" in body
    assert "CredMan" in body
    assert "password" in body.lower()
    example = (ROOT / "airc/config/priority-instances.example.json").read_text(encoding="utf-8")
    assert "password" not in example.lower()
