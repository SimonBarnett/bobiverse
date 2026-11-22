"""BOB-03 pin updated 2026-11-22: no POST /models/validate (form-only); catalog helpers remain."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

BUILD = ROOT / "jeeves/scripts/Build-Jeeves.ps1"
CALLBACK = ROOT / "common/scripts/bobcallback.py"
CATALOG = ROOT / "common/scripts/models_catalog.py"
DOCS = ROOT / "jeeves/docs/webhooks.md"


def test_bob03_models_validate_route_retired():
    text = CALLBACK.read_text(encoding="utf-8")
    assert "MODELS_VALIDATE_PATH" in text
    assert "/bob/v1/models/validate" in text
    # No longer a POST_ROUTES member — returns 404 no_models_validate.
    post = text.split("POST_ROUTES", 1)[1][:500]
    assert "MODELS_VALIDATE_PATH" not in post
    assert "no_models_validate" in text
    cat = CATALOG.read_text(encoding="utf-8")
    assert "MODELS_VALIDATE_PATH = \"/bob/v1/models/validate\"" in cat
    assert "def validate_combo" in cat
    assert "models-valid-combos.json" in cat


def test_bob03_build_jeeves_hidden_import_models_catalog():
    text = BUILD.read_text(encoding="utf-8")
    assert "models_catalog" in text
    assert "--hidden-import" in text


def test_bob03_webhooks_md_documents_form_only_validation():
    text = DOCS.read_text(encoding="utf-8")
    assert "no" in text.lower() and "models/validate" in text
    assert "form" in text.lower() and "dropdown" in text.lower()
    assert "no_models_validate" in text or "form-only" in text.lower()
