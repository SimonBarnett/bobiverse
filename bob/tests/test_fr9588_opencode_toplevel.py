# -*- coding: utf-8 -*-
"""FR #9588: Workers OpenCode Free / OpenCode Paid are top-level siblings (not submenu)."""
from __future__ import annotations

from repo_layout import REPO

TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
DOCS = REPO / "bob" / "docs" / "bob-tray-dialogs.md"
UI03 = REPO / "bob" / "docs" / "bob-tray-ui-03-opencode-free-paid.md"
FIXTURE = REPO / "bob" / "tests" / "fixtures" / "models-catalog-opencode.json"


def test_fr9588_tipform_toplevel_labels_and_tags():
    cs = TRAY.read_text(encoding="utf-8-sig")
    assert "void AddOpencodeTopLevelChoices" in cs
    assert "AddOpencodeModelSubmenu" not in cs
    assert 'string freeText = "OpenCode Free"' in cs
    assert 'string paidText = "OpenCode Paid"' in cs
    assert 'AddAgentChoice(parent, "opencode|free", freeText' in cs
    assert 'AddAgentChoice(parent, "opencode|paid", paidText' in cs
    assert 'MenuItems.Add("Open Code")' not in cs.split("void AddOpencodeTopLevelChoices", 1)[1].split(
        "string ModelsCatalogPath", 1
    )[0]
    assert "top-level Free|Paid" in cs
    assert "submenu Free|Paid" not in cs
    seed = cs[cs.index("void SeedAgentChoices") : cs.index("void SeedAgentChoices") + 900]
    assert "AddOpencodeTopLevelChoices" in seed


def test_fr9588_watch_builds_toplevel_rows():
    ps = WATCH.read_text(encoding="utf-8-sig")
    assert "top-level Free|Paid (FR #9588)" in ps
    assert "submenu Free|Paid" not in ps
    assert "'OpenCode Free'" in ps and "'OpenCode Paid'" in ps
    assert "opencode|{0}" in ps
    assert "EndsWith('|paid')" in ps
    assert "Get-BobTrayOpencodeWebhookModel" in ps


def test_fr9588_click_still_uses_weights_webhook_rows():
    cs = TRAY.read_text(encoding="utf-8-sig")
    assert "OpencodeWebhookModel(catalog, rowAgent)" in cs
    assert 'env["BOB_OPENCODE_MODEL"]' in cs
    assert 'OpencodeWebhookModel(catalog, "Opencode-Free")' in cs
    assert FIXTURE.is_file()


def test_fr9588_docs_pin():
    assert UI03.is_file()
    ui = UI03.read_text(encoding="utf-8")
    assert "9588" in ui
    assert "OpenCode Free" in ui and "OpenCode Paid" in ui
    assert "top-level" in ui.lower() or "sibling" in ui.lower()
    text = DOCS.read_text(encoding="utf-8")
    assert "OpenCode Free" in text and "OpenCode Paid" in text
    assert "Open Code is a submenu" not in text
