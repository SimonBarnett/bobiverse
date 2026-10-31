"""FR #5587: ou is parent-container DN (not OU/DC-only filter)."""
from __future__ import annotations

import airc_network as nw


def test_fr5587_ou_cn_computers_keeps_container():
    dn = "CN=REDQUEEN,CN=Computers,DC=wonderland,DC=local"
    assert nw.ou_from_dn(dn) == "CN=Computers,DC=wonderland,DC=local"


def test_fr5587_ou_domain_controllers_keeps_ou():
    dn = "CN=WALRUS,OU=Domain Controllers,DC=wonderland,DC=local"
    assert nw.ou_from_dn(dn) == "OU=Domain Controllers,DC=wonderland,DC=local"


def test_fr5587_ou_nested_ou():
    dn = "CN=pc-ok,OU=Laptops,OU=Sites,DC=example,DC=invalid"
    assert nw.ou_from_dn(dn) == "OU=Laptops,OU=Sites,DC=example,DC=invalid"


def test_fr5587_ou_escaped_comma_in_rdn():
    dn = r"CN=a\,b,OU=PCs,DC=ex,DC=local"
    assert nw.ou_from_dn(dn) == "OU=PCs,DC=ex,DC=local"


def test_fr5587_ou_unknown_empty_and_single_rdn():
    assert nw.ou_from_dn("") == "unknown"
    assert nw.ou_from_dn(None) == "unknown"
    assert nw.ou_from_dn("CN=solo") == "unknown"
    assert nw.ou_from_dn("   ") == "unknown"


def test_fr5587_inventory_work_uses_parent_container():
    body = nw.inventory_work(
        "diag",
        ldap_enum=lambda: [
            {"hostname": "REDQUEEN", "dn": "CN=REDQUEEN,CN=Computers,DC=wonderland,DC=local"},
            {"hostname": "WALRUS", "dn": "CN=WALRUS,OU=Domain Controllers,DC=wonderland,DC=local"},
        ],
        resolve_ips=lambda _h: [],
    )
    by = {h["hostname"]: h for h in body["hosts"]}
    assert by["REDQUEEN"]["ou"] == "CN=Computers,DC=wonderland,DC=local"
    assert by["WALRUS"]["ou"] == "OU=Domain Controllers,DC=wonderland,DC=local"
