# -*- coding: utf-8 -*-
"""FR #9263 / BOB-TRAY-UI-03: Workers > Open Code is Free|Paid only; Weights model at click."""
from __future__ import annotations

from repo_layout import REPO

TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
FIXTURE = REPO / "bob" / "tests" / "fixtures" / "models-catalog-opencode.json"
DOCS = REPO / "bob" / "docs" / "bob-tray-ui-03-opencode-free-paid.md"


def test_fr9263_tipform_submenu_free_paid_only():
    cs = TRAY.read_text(encoding="utf-8-sig")
    assert "void AddOpencodeModelSubmenu" in cs
    assert 'string freeText = "Free"' in cs
    assert 'string paidText = "Paid"' in cs
    assert 'AddAgentChoice(oc, "opencode|free", freeText' in cs
    assert 'AddAgentChoice(oc, "opencode|paid", paidText' in cs
    assert "Start free model" not in cs.split("void AddOpencodeModelSubmenu", 1)[1].split("void OnAgentChoiceClick", 1)[0]
    assert 'OpencodeWebhookModel(catalog, "Opencode-Free")' in cs
    assert "submenu Free|Paid" in cs


def test_fr9263_watch_builds_free_paid_submenu():
    ps = WATCH.read_text(encoding="utf-8-sig")
    assert "submenu Free|Paid (FR #9263)" in ps
    assert "opencode|{0}" in ps
    assert "'Free'" in ps and "'Paid'" in ps
    assert "EndsWith('|paid')" in ps
    assert "Get-BobTrayOpencodeWebhookModel" in ps
    assert "'Opencode-Free'" in ps
    assert "'Opencode'" in ps


def test_fr9263_click_still_uses_weights_webhook_rows():
    cs = TRAY.read_text(encoding="utf-8-sig")
    assert "OpencodeWebhookModel(catalog, rowAgent)" in cs
    assert 'env["BOB_OPENCODE_MODEL"]' in cs
    assert '"Opencode-Free"' in cs
    assert FIXTURE.is_file()


def test_fr9263_docs_pin():
    assert DOCS.is_file()
    text = DOCS.read_text(encoding="utf-8")
    assert "Free" in text and "Paid" in text
    assert "9263" in text
