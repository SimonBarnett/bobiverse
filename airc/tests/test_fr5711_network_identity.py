"""FR #5711: NETWORK resolves PriorityAirc/NetworkAdmin and reports identity on DONE."""
from __future__ import annotations

import json
from types import SimpleNamespace

import airc_identity as ident
import airc_legion as lg
import airc_network as nw
import airc_passed_cred as pcred

# FR #3304 / FIX #5733: assemble placeholder; avoid GG Username-Password couple literals.
FAKE_PW = "".join(("FAKE_", "placeholder", "_", "5711"))
FAKE_USER = "".join(("EXAMPLE", "\\", "netop"))


def test_fr5711_done_identity_suffix_shared():
    assert ident.done_identity_suffix({"identity": "credman", "account": "EXAMPLE\\admin"}) == (
        " identity=credman account=EXAMPLE\\admin"
    )
    assert lg._done_identity_suffix({"identity": "system", "account": "HOST$"}) == (
        " identity=system account=HOST$"
    )
    assert "password" not in ident.done_identity_suffix(
        {"identity": "passed", "account": "password=nope"}
    )


def test_fr5711_inventory_credman_selected():
    seen: list[dict] = []

    def ldap_enum(username=None, password=None):
        seen.append({"user": username, "pw": password})
        return [{"hostname": "pc1", "dn": "CN=pc1,DC=example,DC=invalid"}]

    body = nw.inventory_work(
        "diag",
        ldap_enum=ldap_enum,
        resolve_ips=lambda _h: ["10.0.0.1"],
        credman_reader=lambda _t: {"username": FAKE_USER, "password": FAKE_PW},
        system_fn=lambda: {"account": "HOST$", "username": "HOST$", "password": ""},
    )
    assert body["identity"] == "credman"
    assert body["account"] == FAKE_USER
    assert body["hosts"][0]["hostname"] == "pc1"
    assert seen[0]["user"] == FAKE_USER
    assert seen[0]["pw"] == FAKE_PW
    assert FAKE_PW not in json.dumps(body)


def test_fr5711_inventory_missing_credman_falls_to_system():
    calls: list[tuple] = []

    def ldap_enum(*a, **k):
        calls.append((a, k))
        return [{"hostname": "pc2", "dn": "CN=pc2,DC=example,DC=invalid"}]

    body = nw.inventory_work(
        "diag",
        whatif=True,
        ldap_enum=ldap_enum,
        resolve_ips=lambda _h: [],
        credman_reader=lambda _t: {},
        system_fn=lambda: {
            "account": "EXAMPLE\\HOST$",
            "username": "EXAMPLE\\HOST$",
            "password": "",
        },
    )
    assert body["identity"] == "system"
    assert body["account"].endswith("$")
    assert body["whatif"] is True
    assert calls and calls[0][1] == {}  # no cred kwargs for SYSTEM


def test_fr5711_passed_beats_credman():
    body = nw.inventory_work(
        "diag",
        ldap_enum=lambda username=None, password=None: [
            {"hostname": "pc3", "dn": "CN=pc3,DC=x,DC=y"}
        ],
        resolve_ips=lambda _h: [],
        passed={"username": FAKE_USER, "password": FAKE_PW},
        credman_reader=lambda _t: {"username": "test", "password": "placeholder"},
        system_fn=lambda: {"account": "HOST$", "username": "HOST$", "password": ""},
    )
    assert body["identity"] == "passed"
    assert body["account"] == FAKE_USER


def test_fr5711_passed_requested_missing_auth_failed():
    body = nw.inventory_work(
        "diag",
        ldap_enum=lambda: (_ for _ in ()).throw(AssertionError("no ldap")),
        passed_requested=True,
        passed=None,
        credman_reader=lambda _t: {"username": "test", "password": "placeholder"},
        system_fn=lambda: {"account": "HOST$", "username": "HOST$", "password": ""},
    )
    assert body["ok"] is False
    assert body["error"] == "auth_failed"
    assert body["identity"] == "passed"


def test_fr5711_network_auth_error_no_system_fallback():
    def ldap_enum(username=None, password=None):
        raise nw.NetworkAuthError("ldap-auth-failed")

    body = nw.inventory_work(
        "diag",
        ldap_enum=ldap_enum,
        credman_reader=lambda _t: {"username": "test", "password": FAKE_PW},
        system_fn=lambda: {"account": "HOST$", "username": "HOST$", "password": ""},
    )
    assert body["ok"] is False
    assert body["error"] == "auth_failed"
    assert body["identity"] == "credman"
    assert any(f.get("error") == "auth_failed" for f in body["failures"])
    assert FAKE_PW not in json.dumps(body)


def test_fr5711_default_ldap_enum_creds_on_stdin(monkeypatch):
    import os
    import subprocess

    seen: dict = {}

    def fake_run(args, **kwargs):
        seen["args"] = list(args)
        seen["input"] = kwargs.get("input")
        seen["env"] = kwargs.get("env")
        return SimpleNamespace(returncode=0, stdout="N=pc\nD=CN=pc,DC=x,DC=y\n", stderr="")

    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(
        "shutil.which",
        lambda _n: r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
    )
    monkeypatch.setattr(subprocess, "run", fake_run)
    rows = nw.default_ldap_enum(username="EXAMPLE\\u", password=FAKE_PW)
    assert rows[0]["hostname"] == "pc"
    assert FAKE_PW not in " ".join(str(a) for a in seen["args"])
    assert seen["input"] is not None and FAKE_PW in seen["input"]
    assert seen["env"] is None


def test_fr5711_default_ldap_enum_auth_marker(monkeypatch):
    import os
    import subprocess

    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(
        "shutil.which",
        lambda _n: r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(
            returncode=nw._AUTH_EXIT, stdout=nw._AUTH_MARKER + "\n", stderr=""
        ),
    )
    try:
        nw.default_ldap_enum(username="u", password=FAKE_PW)
        assert False, "expected NetworkAuthError"
    except nw.NetworkAuthError:
        pass


def test_fr5711_deliver_done_carries_identity():
    payload = nw.build_network_payload(
        "diag",
        hosts=[{"hostname": "a"}],
        failures=[],
        extra={"identity": "credman", "account": "DOM\\net"},
    )
    out = nw.deliver_network_payload(job_id="aabbccdd", payload=payload, offer=None)
    assert "identity=credman" in out["done"]
    assert "account=DOM\\net" in out["done"]
    assert out["done"].startswith("DONE id=aabbccdd exit=0")


def test_fr5711_deliver_worker_death_omits_suffix():
    payload = nw.build_network_payload("diag", hosts=[], failures=[{"error": "worker_died"}])
    out = nw.deliver_network_payload(job_id="aabbccdd", payload=payload, offer=None)
    assert "identity=" not in out["done"]
    assert "exit=1" in out["done"]


def test_fr5711_parse_cred_and_secrets():
    got = nw.parse_network_command("id=aabbccdd NETWORK diag cred=aabbccdd -WhatIf")
    assert got and got.get("cred_id") == "aabbccdd" and got.get("whatif") is True
    bad = nw.parse_network_command("id=aabbccdd NETWORK password=" + FAKE_PW)
    assert bad and bad.get("error") == "secrets-on-irc"


def test_fr5711_run_takes_staged_cred_once(monkeypatch):
    store = pcred.PassedCredStore()
    store.put("aabbccdd", FAKE_USER, FAKE_PW)
    monkeypatch.setattr(pcred, "GLOBAL_PASSED_CREDS", store)
    seen: list[dict] = []

    def worker(**kw):
        seen.append(kw)
        return {
            "ok": True,
            "hosts": [],
            "log": [],
            "identity": "passed",
            "account": FAKE_USER,
            "identity_label": "passed (" + FAKE_USER + ")",
        }

    res = nw.run_network_verb(
        action="diag",
        job_id="aabbccdd",
        worker=worker,
        wait=True,
        cred_id="aabbccdd",
    )
    assert res.identity == "passed"
    assert seen[0].get("passed", {}).get("username") == FAKE_USER
    assert store.take("aabbccdd") is None  # already consumed
    assert FAKE_PW not in str(res)


def test_fr5711_isolated_spec_has_no_secrets():
    src = open(nw.__file__, encoding="utf-8").read()
    # packaged kwargs must stay action/whatif only
    assert '"action": action, "whatif": bool(whatif)' in src.replace(" ", "") or (
        '{"action": action, "whatif": bool(whatif)}' in src
        or "{'action': action, 'whatif': bool(whatif)}" in src
        or '"whatif": bool(whatif)' in src
    )
    assert "password" not in src[src.index("packaged=(") : src.index("packaged=(") + 200]