"""FR #5448: NETWORK fail-closed ldap=false (workgroup / no-DC), not a 'No LDAP' docstring."""
from __future__ import annotations

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
    assert nw.default_ldap_enum() == []


def test_fr5448_mrb5367_pin_targets_contract_not_no_ldap_phrase():
    pin = (ROOT / "airc" / "tests" / "test_mrb5367_hostile_network_verb.py").read_text(encoding="utf-8")
    src = (ROOT / "airc" / "scripts" / "airc_network.py").read_text(encoding="utf-8")
    assert '"No LDAP" in src' not in pin
    assert "workgroup-or-no-dc" in pin or "ldap" in pin.lower()
    assert "airc-network-worker" in src
    assert '"ldap": False' in src or '"ldap": ldap_ok' in src
