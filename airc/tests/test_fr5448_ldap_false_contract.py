"""FR #5448: NETWORK fail-closed ldap=false (workgroup / no-DC), not a 'No LDAP' docstring.

FR #5559: do not assert live ``default_ldap_enum() == []`` --- after FR #5521 the
helper queries ADSI and returns real hosts on domain-joined seats.
"""
from __future__ import annotations

import os

import airc_network as nw
from repo_layout import ROOT


def test_fr5448_stub_and_empty_enum_are_ldap_false():
    stub = nw.stub_network_work("diag", whatif=False)
    assert stub.get("ldap") is False
    assert stub.get("hosts") == []
    empty = nw.inventory_work("diag", ldap_enum=lambda: [])
    assert empty.get("ldap") is False
    assert empty.get("hosts") == []
    assert empty.get("limit") == "workgroup-or-no-dc"


def test_fr5559_live_default_ldap_enum_shape_not_forced_empty():
    """Live enum may be [] (workgroup) or a list of hostname/dn dicts (domain)."""
    rows = nw.default_ldap_enum()
    assert isinstance(rows, list)
    for row in rows:
        if isinstance(row, dict):
            assert "hostname" in row
            assert str(row.get("hostname") or "").strip()
        else:
            assert str(row).strip()
    # Domain-joined boxes must not be forced empty by this contract (FR #5559).
    if os.name == "nt" and rows:
        assert all(
            isinstance(r, dict) and "hostname" in r for r in rows
        ), "FR #5521 shape: hostname+dn dicts"


def test_fr5448_mrb5367_pin_targets_contract_not_no_ldap_phrase():
    pin = (ROOT / "airc" / "tests" / "test_mrb5367_hostile_network_verb.py").read_text(
        encoding="utf-8"
    )
    src = (ROOT / "airc" / "scripts" / "airc_network.py").read_text(encoding="utf-8")
    assert '"No LDAP" in src' not in pin
    assert "workgroup-or-no-dc" in pin or "ldap" in pin.lower()
    assert "airc-network-worker" in src
    assert '"ldap": False' in src or '"ldap": ldap_ok' in src
    # FR #5559: this file must not reintroduce the live-empty assert.
    this = (ROOT / "airc" / "tests" / "test_fr5448_ldap_false_contract.py").read_text(
        encoding="utf-8"
    )
    assert "assert nw.default_ldap_enum() == []" not in this
    assert "FR #5559" in this
