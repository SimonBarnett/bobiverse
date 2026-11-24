# -*- coding: utf-8 -*-
"""FR #9263 / BOB-TRAY-UI-03 (superseded shape by FR #9588): Free|Paid fuel slots; Weights model at click.

FR #9588 flattens the Open Code submenu into top-level OpenCode Free / OpenCode Paid.
This file keeps the Free|Paid + webhook pins and follows the new menu shape.
"""
from __future__ import annotations

from repo_layout import REPO

TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
FIXTURE = REPO / "bob" / "tests" / "fixtures" / "models-catalog-opencode.json"
DOCS = REPO / "bob" / "docs" / "bob-tray-ui-03-opencode-free-paid.md"


def test_fr9263_tipform_free_paid_only():
    cs = TRAY.read_text(encoding="utf-8-sig")
    assert "void AddOpencodeTopLevelChoices" in cs
    assert 'string freeText = "OpenCode Free"' in cs
    assert 'string paidText = "OpenCode Paid"' in cs
    assert 'AddAgentChoice(parent, "opencode|free", freeText' in cs
    assert 'AddAgentChoice(parent, "opencode|paid", paidText' in cs
    block = cs.split("void AddOpencodeTopLevelChoices", 1)[1].split("void OnAgentChoiceClick", 1)[0]
    assert "Start free model" not in block
    assert 'OpencodeWebhookModel(catalog, "Opencode-Free")' in cs
    assert "top-level Free|Paid" in cs


def test_fr9263_watch_builds_free_paid_rows():
    ps = WATCH.read_text(encoding="utf-8-sig")
    assert "top-level Free|Paid (FR #9588)" in ps
    assert "opencode|{0}" in ps
    assert "'OpenCode Free'" in ps and "'OpenCode Paid'" in ps
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
    assert "9588" in text
