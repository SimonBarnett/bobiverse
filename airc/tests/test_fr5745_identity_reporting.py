"""FR #5745: configurable CredMan targets and observable remote identity fallback."""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

import airc_console as ac
import airc_credman
import airc_extension as ex
import airc_identity as ident
import airc_isolated as iso
import airc_legion as lg
import airc_network as nw
from airc_auth_helpers import ops_auth


FAKE_PW = "FAKE_" + "5745_redaction"
TARGETS = {verb: f"TestAirc/{verb}" for verb in ident.DEFAULT_TARGETS}


@pytest.mark.parametrize("source", ["passed", "credman", "system"])
@pytest.mark.parametrize("transport", ["dcc", "dcc-fail", "irc"])
def test_extension_json_and_done_identity(source, transport):
    data = {
        "ok": True, "hosts": [], "failures": [],
        "identity": source, "account": "TEST\\operator" if source != "system" else "TEST\\HOST$",
        "identity_label": f"{source} (TEST)", "password": FAKE_PW,
    }
    log = ex.extension_log_from_payload("install", payload=data)
    assert log["identity"] == source
    assert log["account"] == data["account"]
    assert log["identity_label"] == data["identity_label"]
    sent = []

    def send(raw, offer):
        if transport == "dcc-fail":
            raise OSError("transport unavailable")
        sent.append(json.loads(raw))

    delivered = ex.deliver_extension_log(
        job_id="aabbccdd", log=log, offer=object() if transport != "irc" else None,
        send_fn=send,
    )
    assert f"identity={source}" in delivered["done"]
    assert f"account={data['account']}" in delivered["done"]
    assert FAKE_PW not in json.dumps(log) + str(delivered)
    if sent:
        assert sent[0]["identity"] == source


@pytest.mark.parametrize("error", [None, "winerror-5", FAKE_PW])
def test_safe_fallback_reason(error):
    resolved = ident.resolve_remote_identity(
        verb="legion", credman_target=TARGETS["legion"],
        credman_reader=lambda t: {"__error__": error} if error else {},
        system_fn=lambda: {"account": "TEST\\HOST$"},
    )
    expected = (
        f"credman-missing:{TARGETS['legion']}" if error is None
        else "credman-read-error:winerror-5" if error == "winerror-5"
        else "credman-read-error:read-failed"
    )
    assert resolved.public_dict()["identity_reason"] == expected
    assert FAKE_PW not in str(resolved.public_dict())


def test_native_reader_error_is_safe(monkeypatch):
    def read(target):
        raise airc_credman.CredmanError("winerror-5")

    monkeypatch.setattr(airc_credman, "read_generic_credential", read)
    assert ident.default_credman_reader("test") == {"__error__": "winerror-5"}


def test_raised_reader_error_is_safe():
    def read(target):
        raise RuntimeError(FAKE_PW)

    resolved = ident.resolve_remote_identity(credman_reader=read)
    assert resolved.identity_reason == "credman-read-error:read-failed"
    assert FAKE_PW not in str(resolved.public_dict())


@pytest.mark.parametrize("verb", ["legion", "extension", "network"])
@pytest.mark.parametrize("source", ["credman", "system"])
def test_console_config_worker_json_and_fallback_log(tmp_path, monkeypatch, verb, source):
    config = tmp_path / "config"
    config.mkdir()
    (config / "airc.json").write_text(json.dumps({"credman_targets": TARGETS}))
    read_targets = []
    logs = []
    deliveries = []

    def read(target):
        read_targets.append(target)
        return {"username": "TEST\\admin", "password": FAKE_PW} if source == "credman" else {}

    monkeypatch.setattr(ident, "default_credman_reader", read)

    def legion(**kw):
        return lg.run_legion_verb(
            wait=True, worker=lambda target, **opts: lg.installer_legion_work(
                target, run_fn=lambda spec, **secret: {"ok": True}, **opts
            ), **kw,
        )

    def extension(**kw):
        return ex.run_extension_verb(
            wait=True, worker=lambda **opts: ex.fill_holes_work(
                ldap_enum=lambda: [], dc_enum=lambda: [], **opts
            ), **kw,
        )

    def network(**kw):
        return nw.run_network_verb(
            wait=True, worker=lambda **opts: nw.inventory_work(
                ldap_enum=lambda **secret: [], **opts
            ), **kw,
        )

    core = ac.AircConsoleCore(
        machine="tm", nick="tm_console", auth=ops_auth("op", channel="#tm"),
        install_root=str(tmp_path), identity_fallback_log=logs.append,
        legion_runner=legion, extension_runner=extension, network_runner=network,
    )
    setattr(core, f"{verb}_log_emit", deliveries.append)
    command = {"legion": "LEGION host -WhatIf", "extension": "EXTENSION install",
               "network": "NETWORK diag"}[verb]
    result = core.handle_raw(f":op!u@h PRIVMSG tm_console :id=aabbccdd {command}")
    assert result and result.action == verb
    assert read_targets == [TARGETS[verb]]
    payload = json.loads(deliveries[0]["payload"])
    assert payload["identity"] == source
    if source == "credman":
        assert payload["account"] == "TEST\\admin"
    else:
        assert payload["account"].endswith("$")
    assert payload["account"]
    assert f"identity={source}" in deliveries[0]["done"]
    if source == "system":
        reason = f"credman-missing:{TARGETS[verb]}"
        assert payload["identity_reason"] == reason
        assert len(logs) == 1 and "identity-fallback" in logs[0]
        assert f"identity_reason={reason}" in logs[0]
        assert f"action={verb}" in logs[0]
    else:
        assert not logs
        assert "identity_reason" not in payload
    assert FAKE_PW not in str(deliveries) + str(logs) + str(result)


@pytest.mark.parametrize("verb", ["legion", "extension", "network"])
def test_custom_target_crosses_isolated_worker_spec(monkeypatch, verb):
    specs = []
    monkeypatch.setattr(iso, "is_packaged_work", lambda work: True)
    monkeypatch.setattr(iso, "start_isolated", lambda **kw: specs.append(kw["packaged"]))
    runner = {"legion": lg.run_legion_verb, "extension": ex.run_extension_verb,
              "network": nw.run_network_verb}[verb]
    runner(credman_target=TARGETS[verb])
    assert specs[0][2]["credman_target"] == TARGETS[verb]
    assert FAKE_PW not in json.dumps(specs)


def test_config_defaults_and_invalid_overrides():
    assert ident.configured_credman_targets(None) == ident.DEFAULT_TARGETS
    assert ident.configured_credman_targets({"legion": "", "network": 42,
                                            "extension": "bad\nlog"}) == ident.DEFAULT_TARGETS
    targets = ident.configured_credman_targets({"legion": " TestAirc/Custom "})
    assert targets["legion"] == "TestAirc/Custom"
    assert targets["network"] == ident.DEFAULT_TARGETS["network"]


def test_extension_gpo_custom_target(monkeypatch):
    calls = []

    def run(args, **kw):
        calls.append(args)
        return type("Result", (), {"returncode": 0, "stdout": '{"ok":true}', "stderr": ""})()

    monkeypatch.setattr(ex.subprocess, "run", run)
    ex.run_extension_gpo_work(credman_target=TARGETS["extension"])
    args = calls[0]
    assert args[args.index("-CredmanTarget") + 1] == TARGETS["extension"]
    script = Path(ex.__file__).with_name("Invoke-AircExtensionGpo.ps1").read_text()
    assert "Get-ExtensionAdminCredential -Target $CredmanTarget" in script


def test_network_passed_credentials_stay_in_parent_thread(monkeypatch):
    done = threading.Event()
    monkeypatch.setattr(iso, "is_packaged_work", lambda work: True)

    def isolated(**kw):
        raise AssertionError("passed credentials must not enter IPC")

    monkeypatch.setattr(iso, "start_isolated", isolated)
    nw.run_network_verb(
        passed={"username": "TEST\\admin", "password": FAKE_PW},
        credman_target=TARGETS["network"],
        worker=lambda **kw: nw.inventory_work(ldap_enum=lambda **secret: [], **kw),
        on_done=lambda res: done.set(),
    )
    assert done.wait(2)
