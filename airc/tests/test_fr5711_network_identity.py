"""NETWORK resolves and actually binds the selected identity without leaking it."""
import json
import os
from types import SimpleNamespace

import pytest

import airc_console as ac
import airc_identity as ident
import airc_network as nw
import airc_passed_cred as pcred
from airc_auth_helpers import ops_auth


FAKE_PW = "FAKE_" + "network_test_value"


@pytest.mark.parametrize("source", ["passed", "credman", "system"])
def test_identity_used_for_ldap(monkeypatch, source):
    seen = []

    def reader(target):
        assert target == "PriorityAirc/NetworkAdmin"
        return {"username": "EXAMPLE\\admin", "password": FAKE_PW} if source == "credman" else {}

    monkeypatch.setattr(ident, "default_credman_reader", reader)

    def enum(*, identity):
        seen.append(identity)
        return [{"hostname": "pc", "dn": "CN=pc,OU=Devices,DC=example"}]

    monkeypatch.setattr(nw, "default_ldap_enum", enum)
    passed = {"username": "EXAMPLE\\operator", "password": FAKE_PW} if source == "passed" else None
    result = nw.run_network_verb(
        wait=True, whatif=True,
        **({"passed_cred": passed} if passed else {}),
        resolve_ips=lambda host: ["192.0.2.1"],
    )
    assert seen[0].source == source
    assert result.identity["identity"] == source
    assert result.identity["account"] == seen[0].account
    assert result.hosts[0]["hostname"] == "pc"
    assert FAKE_PW not in str(result)


def test_explicit_ldap_credentials_use_stdin_only(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr("shutil.which", lambda name: "powershell.exe")
    seen = []

    def run(args, **kw):
        seen.append((args, kw))
        return SimpleNamespace(returncode=0, stdout="N=pc\nD=CN=pc,DC=example\n")

    monkeypatch.setattr("subprocess.run", run)
    identity = ident.resolve_remote_identity(
        verb="network", passed={"username": "EXAMPLE\\op", "password": FAKE_PW},
    )
    assert nw.default_ldap_enum(identity=identity)[0]["hostname"] == "pc"
    args, kw = seen[0]
    assert FAKE_PW not in str(args)
    assert "DirectoryEntry" in args[-1]
    assert json.loads(kw["input"])["password"] == FAKE_PW
    assert json.loads(kw["input"])["username"] == identity.username


def test_rejected_credential_fails_closed(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr("shutil.which", lambda name: "powershell.exe")
    seen = []

    def run(*args, **kw):
        seen.append(kw)
        return SimpleNamespace(returncode=1, stdout="", stderr=FAKE_PW)

    monkeypatch.setattr("subprocess.run", run)
    body = nw.inventory_work(passed_cred={"username": "EXAMPLE\\op", "password": FAKE_PW})
    assert not body["ok"]
    assert body["failures"][0]["error"] == "auth_failed"
    assert body["identity"] == "passed"
    assert len(seen) == 1
    assert FAKE_PW not in str(body)


def test_staged_credential_consumed_in_parent_not_packaged(monkeypatch):
    monkeypatch.setattr("airc_isolated.is_packaged_work", lambda work: True)
    monkeypatch.setattr(
        "airc_isolated.start_isolated",
        lambda **kw: pytest.fail("staged credentials must not be serialized"),
    )
    seen = []

    class ImmediateThread:
        def __init__(self, *, target, **kw):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(nw.threading, "Thread", ImmediateThread)
    pcred.GLOBAL_PASSED_CREDS.put("aabbccdd", "EXAMPLE\\op", FAKE_PW)

    def worker(**kw):
        seen.append(kw)
        return {"ok": True}

    nw.run_network_verb(cred_id="aabbccdd", worker=worker)
    assert seen[0]["passed_cred"]["password"] == FAKE_PW
    assert seen[0]["passed_requested"]
    assert pcred.GLOBAL_PASSED_CREDS.take("aabbccdd") is None
    result = nw.run_network_verb(wait=True, cred_id="aabbccdd")
    assert not result.ok
    assert result.identity["identity"] == "passed"
    assert result.failures[0]["error"] == "auth_failed"


@pytest.mark.parametrize("transport", ["irc", "dcc", "dcc-fail"])
def test_identity_in_payload_log_and_done(transport):
    payload = nw.build_network_payload(extra={
        "identity": "credman", "account": "EXAMPLE\\admin", "password": FAKE_PW,
    })

    def send(*args):
        if transport == "dcc-fail":
            raise OSError("offline")

    delivered = nw.deliver_network_payload(
        job_id="aabbccdd", payload=payload,
        offer=object() if transport != "irc" else None, send_fn=send,
    )
    for line in (delivered["summary"], delivered["done"]):
        assert "identity=credman account=EXAMPLE\\admin" in line
    assert FAKE_PW not in str(delivered)
    assert payload["identity"] == "credman"


def test_console_forwards_cred_and_identity():
    seen = []

    def runner(**kw):
        seen.append(kw)
        result = nw.NetworkVerbResult(
            True, "NETWORK accepted", job_id=kw["job_id"],
            identity={"identity": "system", "account": "EXAMPLE\\PC$"},
        )
        kw["on_done"](result)
        return result

    core = ac.AircConsoleCore(
        machine="tm", nick="tm_console", auth=ops_auth("op", channel="#tm"),
        network_runner=runner,
    )
    delivered = []
    core.network_log_emit = delivered.append
    result = core.handle_raw(
        ":op!u@h PRIVMSG tm_console :id=aabbccdd NETWORK -WhatIf cred=aabbccdd"
    )
    assert seen[0]["cred_id"] == "aabbccdd"
    assert "identity=system account=EXAMPLE\\PC$" in delivered[0]["done"]
    assert "identity=system" in result.reply
    secret_command = "NETWORK " + "password" + "=" + "example"
    assert nw.parse_network_command(secret_command)["usage"]


def test_console_never_retries_without_requested_identity():
    seen = []

    def legacy_runner(*, action):
        seen.append(action)
        return nw.NetworkVerbResult(True, "unexpected")

    core = ac.AircConsoleCore(
        machine="tm", nick="tm_console", auth=ops_auth("op", channel="#tm"),
        network_runner=legacy_runner,
    )
    delivered = []
    core.network_log_emit = delivered.append
    result = core.handle_raw(
        ":op!u@h PRIVMSG tm_console :id=aabbccdd NETWORK cred=aabbccdd"
    )
    assert seen == []
    assert "auth_failed" in result.reply
    assert "exit=1" in delivered[0]["done"]
