"""FR #5659: LEGION/EXTENSION identity order passed -> CredMan -> SYSTEM."""
from __future__ import annotations

import json
from pathlib import Path

import airc_console as ac
import airc_identity as ident
import airc_legion as lg
import airc_passed_cred as pcred
from airc_auth_helpers import ops_auth


FAKE_PW = "FAKE_" + "5659_secret_pw"


def test_fr5659_resolve_passed_wins():
    got = ident.resolve_remote_identity(
        verb="legion",
        passed={"username": "WONDERLAND\\admin", "password": FAKE_PW},
        credman_reader=lambda t: {"username": "cred", "password": "x"},
        system_fn=lambda: {"account": "HOST$", "username": "HOST$", "password": ""},
    )
    assert got.source == "passed"
    assert got.account == "WONDERLAND\\admin"
    pub = got.public_dict()
    assert pub["identity"] == "passed"
    assert FAKE_PW not in str(pub)


def test_fr5659_resolve_credman_middle():
    got = ident.resolve_remote_identity(
        verb="legion",
        passed=None,
        credman_reader=lambda t: {"username": "WONDERLAND\\legion", "password": FAKE_PW},
        system_fn=lambda: {"account": "HOST$", "username": "HOST$", "password": ""},
    )
    assert got.source == "credman"
    assert got.account == "WONDERLAND\\legion"
    assert got.credman_target == "PriorityAirc/LegionAdmin"


def test_fr5659_resolve_missing_credman_falls_to_system():
    got = ident.resolve_remote_identity(
        verb="extension",
        passed=None,
        credman_reader=lambda t: {},
        system_fn=lambda: {
            "account": "WONDERLAND\\MARCHHARE$",
            "username": "WONDERLAND\\MARCHHARE$",
            "password": "",
        },
    )
    assert got.source == "system"
    assert got.credman_missing is True
    assert got.account.endswith("$")


def test_fr5659_irc_rejects_plaintext_password():
    assert ident.irc_line_has_plaintext_secret("LEGION flamingo password=" + FAKE_PW)
    assert ident.irc_line_has_plaintext_secret("CRED id=aabbccdd pass=secret")
    assert not ident.irc_line_has_plaintext_secret("LEGION flamingo cred=aabbccdd")


def test_fr5659_legion_parse_secrets_on_irc():
    got = lg.parse_legion_command("id=aabbccdd LEGION flamingo password=" + FAKE_PW)
    assert got and got["error"] == "secrets-on-irc"


def test_fr5659_legion_parse_cred_ref():
    got = lg.parse_legion_command("id=aabbccdd LEGION flamingo cred=aabbccdd -WhatIf")
    assert got and got["error"] is None
    assert got["cred_id"] == "aabbccdd"
    assert got["target"] == "flamingo"
    assert got["whatif"] is True


def test_fr5659_legion_passed_identity(monkeypatch):
    monkeypatch.setattr(
        lg,
        "read_remote_airc_profile_result",
        lambda host, **_k: {"profile": "", "ok": True, "found": False, "detail": "not-found"},
    )
    monkeypatch.setattr(
        ident,
        "default_credman_reader",
        lambda t: {"username": "should-not", "password": "x"},
    )
    seen: list[dict] = []

    def run_fn(spec, secret=""):
        seen.append({"spec": spec, "secret": secret})
        return {"ok": True, "status": "ok"}

    body = lg.installer_legion_work(
        "flamingo",
        whatif=False,
        run_fn=run_fn,
        passed_cred={"username": "WONDERLAND\\op", "password": FAKE_PW},
    )
    assert body["identity"] == "passed"
    assert body["account"] == "WONDERLAND\\op"
    assert "passed" in body["identity_label"]
    assert FAKE_PW not in str(body)
    assert seen[0]["secret"] == FAKE_PW
    assert seen[0]["spec"]["password_via"] == "passed"
    assert FAKE_PW not in json.dumps(seen[0]["spec"])


def test_fr5659_legion_wrong_passed_auth_failed_no_fallback(monkeypatch):
    monkeypatch.setattr(
        lg,
        "read_remote_airc_profile_result",
        lambda host, **_k: {"profile": "", "ok": True, "found": False, "detail": "not-found"},
    )
    monkeypatch.setattr(
        ident,
        "default_credman_reader",
        lambda t: {"username": "cred", "password": "other"},
    )

    def run_fn(spec, secret=""):
        return {"ok": False, "status": "failed", "error": "Access is denied"}

    body = lg.installer_legion_work(
        "flamingo",
        whatif=False,
        run_fn=run_fn,
        passed_cred={"username": "WONDERLAND\\bad", "password": FAKE_PW},
    )
    assert body["ok"] is False
    assert body["error"] == "auth_failed"
    assert body["identity"] == "passed"
    assert FAKE_PW not in str(body)


def test_fr5659_legion_missing_credman_falls_to_system(monkeypatch):
    monkeypatch.setattr(ident, "default_credman_reader", lambda t: {})
    seen: list[dict] = []

    def run_fn(spec):
        seen.append(spec)
        return {"ok": True, "status": "ok"}

    body = lg.installer_legion_work("flamingo", whatif=False, run_fn=run_fn)
    assert body["identity"] == "system"
    assert body.get("credman_missing") is True
    assert body["credman_fell_through"] == "system"
    assert body["ok"] is True
    assert "username" not in seen[0]


def test_fr5659_legion_credman_source(monkeypatch):
    monkeypatch.setattr(
        lg,
        "read_remote_airc_profile_result",
        lambda host, **_k: {"profile": "", "ok": True, "found": False, "detail": "not-found"},
    )
    monkeypatch.setattr(
        ident,
        "default_credman_reader",
        lambda t: {"username": "WONDERLAND\\legion", "password": FAKE_PW},
    )
    seen: list[dict] = []

    def run_fn(spec, secret=""):
        seen.append({"spec": spec, "secret": secret})
        return {"ok": True, "status": "ok"}

    body = lg.installer_legion_work("walrus", whatif=True, run_fn=run_fn)
    assert body["identity"] == "credman"
    assert body["account"] == "WONDERLAND\\legion"
    assert seen[0]["spec"]["password_via"] == "credman"
    assert FAKE_PW not in str(body)


def test_fr5659_passed_store_take_oneshot_and_ttl():
    store = pcred.PassedCredStore()
    store.put("aabbccdd", "u", FAKE_PW, ttl_s=60)
    assert store.peek("aabbccdd")["password"] == FAKE_PW
    assert store.take("aabbccdd")["username"] == "u"
    assert store.take("aabbccdd") is None


def test_fr5659_cred_json_and_command_parse():
    assert pcred.parse_cred_json('{"username":"a","password":"' + FAKE_PW + '"}')[
        "username"
    ] == "a"
    cmd = pcred.parse_cred_command("id=aabbccdd CRED via=dcc")
    assert cmd and cmd["via"] == "dcc" and cmd["qid"] == "aabbccdd"


def test_fr5659_console_rejects_password_on_legion():
    auth = ops_auth("op", channel="#tm")
    core = ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        nick="tm_console",
        legion_runner=lambda **kw: lg.LegionVerbResult(True, "accepted"),
    )
    hr = core.handle_raw(
        ":op!u@h PRIVMSG tm_console :id=aabbccdd LEGION flamingo password=" + FAKE_PW
    )
    assert hr
    assert "secrets-on-irc" in (hr.reply or "")
    assert FAKE_PW not in (hr.reply or "")


def test_fr5659_console_cred_requires_dcc():
    auth = ops_auth("op", channel="#tm")
    core = ac.AircConsoleCore(machine="tm", auth=auth, nick="tm_console")
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=aabbccdd CRED id=aabbccdd")
    assert hr
    assert "cred-requires-dcc" in (hr.reply or "")


def test_fr5659_deliver_done_carries_identity():
    log = lg.build_legion_log(
        target="flamingo",
        summary="ok",
        extra={
            "identity": "system",
            "identity_source": "system",
            "account": "WONDERLAND\\HOST$",
        },
    )
    out = lg.deliver_legion_log(job_id="aabbccdd", log=log, offer=None)
    assert "identity=system" in out["done"]
    assert "account=WONDERLAND\\HOST$" in out["done"]
    assert FAKE_PW not in out["done"]


def test_fr5659_redaction_grep_logs_and_replies(monkeypatch):
    monkeypatch.setattr(
        ident,
        "default_credman_reader",
        lambda t: {"username": "u", "password": FAKE_PW},
    )
    body = lg.installer_legion_work(
        "flamingo",
        whatif=True,
        run_fn=lambda spec, secret="": {"ok": True, "status": "dry-run"},
    )
    log = lg.build_legion_log(
        target="flamingo",
        summary=body.get("status") or "",
        extra={
            "identity": body["identity"],
            "identity_label": body["identity_label"],
            "account": body["account"],
        },
    )
    delivered = lg.deliver_legion_log(job_id="aabbccdd", log=log, offer=None)
    blob = json.dumps(body) + json.dumps(log) + str(delivered)
    assert FAKE_PW.lower() not in blob.lower()
    assert "password=" not in blob.lower()


def test_fr5659_docs_and_skills_mention_order():
    root = Path(lg.__file__).resolve().parents[1]
    skill = (root / ".grok/skills/bobiverse-airc-commands/SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "FR #5659" in skill
    assert "CRED" in skill
    assert "via=dcc" in skill
    assert "identity=passed|credman|system" in skill or "identity=passed" in skill
    docs = (root / "docs/airc-remote-control.md").read_text(encoding="utf-8")
    assert "FR #5659" in docs
    troubl = (
        root / ".grok/skills/bobiverse-airc-troubleshooting/SKILL.md"
    ).read_text(encoding="utf-8")
    assert "FR #5659" in troubl
    assert "auth_failed" in troubl
