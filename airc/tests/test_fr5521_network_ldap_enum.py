"""FR #5521: airc_network.default_ldap_enum must query ADSI (not stub [])."""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import airc_network as nw


def test_fr5521_default_ldap_enum_not_empty_stub():
    src = Path(nw.__file__).read_text(encoding="utf-8")
    start = src.index("def default_ldap_enum")
    end = src.index("\ndef default_resolve_ips")
    fn = src[start:end]
    assert "adsisearcher" in fn.lower() or "objectCategory=computer" in fn
    assert "distinguishedName" in fn or "distinguishedname" in fn.lower()
    # Must not be the old unconditional stub.
    assert "Workgroup / no-DC: empty" not in fn


def test_fr5521_default_ldap_enum_parses_adsi_pairs(monkeypatch):
    fake = SimpleNamespace(
        returncode=0,
        stdout=(
            "N=pc-ok\n"
            "D=CN=pc-ok,OU=Laptops,DC=example,DC=invalid\n"
            "N=pc-bad\n"
            "D=CN=pc-bad,OU=Shop,DC=example,DC=invalid\n"
        ),
        stderr="",
    )

    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(
        "shutil.which",
        lambda _n: r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
    )
    monkeypatch.setattr("subprocess.run", lambda *_a, **_k: fake)
    rows = nw.default_ldap_enum()
    assert len(rows) == 2
    assert rows[0]["hostname"] == "pc-ok"
    assert "Laptops" in rows[0]["dn"]

    def resolve(host: str) -> list[str]:
        if host == "pc-ok":
            return ["10.0.0.1"]
        raise OSError("nxdomain")

    body = nw.inventory_work(
        "diag", ldap_enum=nw.default_ldap_enum, resolve_ips=resolve
    )
    assert body["ldap"] is True
    assert {h["hostname"] for h in body["hosts"]} == {"pc-ok", "pc-bad"}
    assert body["hosts"][0]["ou"] != "unknown" or "Laptops" in body["hosts"][0]["ou"]


def test_fr5521_non_windows_still_empty(monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    assert nw.default_ldap_enum() == []


def test_fr5521_adsi_failure_empty_not_invented(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(
        "shutil.which",
        lambda _n: r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
    )
    monkeypatch.setattr(
        "subprocess.run",
        lambda *_a, **_k: SimpleNamespace(returncode=1, stdout="", stderr="no dc"),
    )
    assert nw.default_ldap_enum() == []
    body = nw.inventory_work("diag", ldap_enum=nw.default_ldap_enum)
    assert body["hosts"] == []
    assert body["ldap"] is False
