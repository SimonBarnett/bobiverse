"""FR #5299: NETWORK inventory hostname + ips + OU; no invented hosts."""
from __future__ import annotations

import airc_network as nw


def test_fr5299_domain_fixture_ips_and_ou():
    def ldap():
        return [
            {"hostname": "pc-ok", "dn": "CN=pc-ok,OU=Laptops,DC=example,DC=invalid"},
            {"hostname": "pc-bad", "dn": "CN=pc-bad,OU=Shop,DC=example,DC=invalid"},
        ]

    def resolve(host: str) -> list[str]:
        if host == "pc-ok":
            return ["10.0.0.8"]
        raise OSError("nxdomain")

    body = nw.inventory_work(
        "diag",
        ldap_enum=ldap,
        resolve_ips=resolve,
        extra_hosts=["ghost-box"],
    )
    by = {h["hostname"]: h for h in body["hosts"]}
    assert set(by) == {"pc-ok", "pc-bad"}
    assert by["pc-ok"]["ips"] == ["10.0.0.8"]
    assert "Laptops" in by["pc-ok"]["ou"]
    assert by["pc-bad"]["ips"] == []
    assert any(f.get("host") == "pc-bad" for f in body["log"])
    assert "ghost-box" not in by
    blob = str(body).lower()
    assert "password" not in blob
    assert body.get("ldap") is True


def test_fr5299_workgroup_empty_enum_no_invented():
    body = nw.inventory_work(
        "diag",
        ldap_enum=lambda: [],
        resolve_ips=lambda _h: ["1.2.3.4"],
        extra_hosts=["not-ad"],
    )
    assert body["hosts"] == []
    assert body["ldap"] is False
    assert "workgroup" in str(body.get("limit") or "").lower() or body.get("ldap") is False


def test_fr5299_ou_unknown_without_dn():
    body = nw.inventory_work(
        "diag",
        ldap_enum=lambda: [{"hostname": "solo"}],
        resolve_ips=lambda _h: [],
    )
    assert body["hosts"][0]["ou"] == "unknown"
