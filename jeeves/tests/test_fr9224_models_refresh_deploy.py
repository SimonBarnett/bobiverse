"""FR #9224: models_refresh ships in freeze + pack; IIS admits POST refresh."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

BUILD = ROOT / "jeeves/scripts/Build-Jeeves.ps1"
INSTALL = ROOT / "jeeves/scripts/Install-BobWebhooks.ps1"
PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
DOCS = ROOT / "jeeves/docs/webhooks.md"
CALLBACK = ROOT / "common/scripts/bobcallback.py"
REFRESH = ROOT / "common/scripts/models_refresh.py"


def test_fr9224_models_refresh_source_exists():
    assert REFRESH.is_file()
    text = REFRESH.read_text(encoding="utf-8")
    assert "MODELS_REFRESH_PATH" in text
    assert "/bob/v1/models/refresh" in text


def test_fr9224_bobcallback_imports_models_refresh():
    text = CALLBACK.read_text(encoding="utf-8")
    assert "import models_refresh" in text
    assert "MODELS_REFRESH_PATH" in text


def test_fr9224_build_jeeves_hidden_import_models_refresh():
    text = BUILD.read_text(encoding="utf-8")
    assert "models_refresh" in text
    assert "--hidden-import" in text


def test_fr9224_iis_models_webhook_allows_post():
    text = INSTALL.read_text(encoding="utf-8")
    assert text.count('pattern="^GET|HEAD|POST$"') >= 2
    # Old GET|HEAD-only pattern must be gone from REQUEST_METHOD conditions.
    assert 'pattern="^GET|HEAD$"' not in text


def test_fr9224_pack_asserts_models_refresh_stage():
    text = PACK.read_text(encoding="utf-8")
    assert "Assert-BobiverseStageHasModelsRefresh" in text
    assert r"scripts\models_refresh.py" in text or "scripts\\models_refresh.py" in text


def test_fr9224_webhooks_md_documents_post_iis():
    text = DOCS.read_text(encoding="utf-8")
    assert "GET|HEAD|POST" in text or "forwards GET|HEAD|POST" in text
    assert "models/refresh" in text
