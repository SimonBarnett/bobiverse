"""BOB-03 / FR #8710: pin MODELS_VALIDATE_PATH + models_catalog freeze import (CI=jeeves/tests)."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

BUILD = ROOT / "jeeves/scripts/Build-Jeeves.ps1"
CALLBACK = ROOT / "common/scripts/bobcallback.py"
CATALOG = ROOT / "common/scripts/models_catalog.py"
DOCS = ROOT / "jeeves/docs/webhooks.md"


def test_bob03_models_validate_route_constant():
    text = CALLBACK.read_text(encoding="utf-8")
    assert "MODELS_VALIDATE_PATH" in text
    assert "/bob/v1/models/validate" in text
    assert "MODELS_VALIDATE_PATH" in text.split("POST_ROUTES", 1)[1][:400]
    cat = CATALOG.read_text(encoding="utf-8")
    assert "MODELS_VALIDATE_PATH = \"/bob/v1/models/validate\"" in cat
    assert "MODELS_VALID_COMBOS_NAME" in cat
    assert "def validate_combo" in cat
    assert "def handle_models_validate" in cat
    assert "models-valid-combos.json" in cat


def test_bob03_build_jeeves_hidden_import_models_catalog():
    text = BUILD.read_text(encoding="utf-8")
    assert "models_catalog" in text
    assert "--hidden-import" in text


def test_bob03_webhooks_md_documents_validate():
    text = DOCS.read_text(encoding="utf-8")
    assert "/bob/v1/models/validate" in text
    assert "models-valid-combos.json" in text
    assert "catalog_unavailable" in text
    assert "INFO models validate reject" in text
