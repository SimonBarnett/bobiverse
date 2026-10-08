"""docs/mrb-3613 hostile pins for FR #3450 / PR #3613 hours webhook."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

BOBHOURS = ROOT / "common/scripts/bobhours.py"
CALLBACK = ROOT / "common/scripts/bobcallback.py"
WEBHOOKS = ROOT / "jeeves/docs/webhooks.md"
INSTALL = ROOT / "jeeves/scripts/Install-BobWebhooks.ps1"
PRODUCT_TEST = ROOT / "common/tests/test_fr3450_hours_webhook.py"


def test_mrb3613_source_pins_no_priority_write_and_cred_reject():
    t = BOBHOURS.read_text(encoding="utf-8")
    assert "Nothing here writes to Priority" in t
    assert "FR #3450" in t or "3450" in t
    assert "password" in t and "api_key" in t and "client_secret" in t
    assert "TRANSORDER" not in t
    assert "idempotency_key" in t
    assert "Europe/London" in t or "Europe/London" in WEBHOOKS.read_text(encoding="utf-8")


def test_mrb3613_callback_wires_hours_routes():
    t = CALLBACK.read_text(encoding="utf-8")
    assert "import bobhours" in t
    assert "HOURS_PATH" in t
    assert "is_hours_route" in t or "handle_hours_request" in t
    assert "/bob/v1/hours" in t


def test_mrb3613_iis_and_docs_cite_hours():
    install = INSTALL.read_text(encoding="utf-8")
    assert "BobHoursWebhook" in install
    assert "bob/v1/hours" in install
    docs = WEBHOOKS.read_text(encoding="utf-8")
    assert "FR #3450" in docs
    assert "/bob/v1/hours" in docs
    assert "no secret" in docs.lower() or "No route needs a password" in docs
    skill = (ROOT / "jeeves/.grok/skills/bobiverse-jeeves/SKILL.md").read_text(encoding="utf-8")
    assert "FR #3450" in skill
    assert "/hours" in skill or "bobhours" in skill


def test_mrb3613_product_test_exists_and_covers_routes():
    t = PRODUCT_TEST.read_text(encoding="utf-8")
    assert "test_fr3450" in PRODUCT_TEST.name or "3450" in t
    assert "idempotency" in t.lower() or "idempotency_key" in t
    assert "export" in t.lower()
    assert "credential" in t.lower() or "password" in t.lower()
