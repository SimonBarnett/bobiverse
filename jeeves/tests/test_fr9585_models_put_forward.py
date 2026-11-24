# -*- coding: utf-8 -*-
"""FR #9585: models_put_forward monitor + tip PUT / Weights Save pins."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from repo_layout import REPO

MON = REPO / "jeeves" / "tools" / "monitor"
SCRIPTS = REPO / "jeeves" / "scripts"
INSTALL = SCRIPTS / "Install-BobWebhooks.ps1"
TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
CLIENT = REPO / "bob" / "tray" / "dialogs" / "BobModelsClient.cs"
WEIGHTS = REPO / "bob" / "tray" / "dialogs" / "WeightsForm.cs"
DIALOGS = REPO / "bob" / "docs" / "bob-tray-dialogs.md"
INVOKE = SCRIPTS / "Invoke-JeevesMonitorCheck.ps1"
START = REPO / "jeeves" / ".grok" / "skills" / "monitor-start" / "SKILL.md"


@pytest.fixture()
def mon_path(monkeypatch):
    import sys

    sys.path.insert(0, str(MON))
    import models_put_forward as mpf  # noqa: E402

    return mpf


def test_fr9585_classify_iis_html_404(mon_path):
    html = (
        "<!DOCTYPE html><title>404 - File or directory not found.</title>"
        "<h2>404 - File or directory not found.</h2>"
    )
    row = mon_path.classify_put_result(404, html)
    assert row["iis_html_404"] is True
    assert row["reached_backend"] is False


def test_fr9585_classify_empty_404_as_iis_miss(mon_path):
    row = mon_path.classify_put_result(404, "")
    assert row["iis_html_404"] is True


def test_fr9585_classify_backend_403_peer_reached(mon_path):
    row = mon_path.classify_put_result(403, '{"error":"peer"}')
    assert row["reached_backend"] is True
    assert row["iis_html_404"] is False


def test_fr9585_classify_backend_400_body(mon_path):
    row = mon_path.classify_put_result(400, '{"error":"bad_body"}')
    assert row["reached_backend"] is True


def test_fr9585_check_fixture_iis_404_is_finding(tmp_path, monkeypatch, mon_path):
    fixture = tmp_path / "put.json"
    fixture.write_text(
        json.dumps(
            {
                "http_status": 404,
                "body": "<!DOCTYPE html><title>404 - File or directory not found.</title>",
                "url": "https://bob.ntsa.uk/bob/v1/models",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("JEEVES_MODELS_PUT_FORWARD_FIXTURE", str(fixture))
    payload, code = mon_path.check(None)
    assert code == mon_path.EXIT_FINDING
    assert payload["ok"] is False
    assert payload["probe"]["iis_html_404"] is True
    assert "Install-BobWebhooks" in payload["remediation"]
    assert any("IIS HTML 404" in f for f in payload["findings"])


def test_fr9585_check_fixture_backend_ok(tmp_path, monkeypatch, mon_path):
    fixture = tmp_path / "put.json"
    fixture.write_text(
        json.dumps({"http_status": 403, "body": '{"error":"peer_denied"}'}),
        encoding="utf-8",
    )
    monkeypatch.setenv("JEEVES_MODELS_PUT_FORWARD_FIXTURE", str(fixture))
    payload, code = mon_path.check(None)
    assert code == mon_path.EXIT_OK
    assert payload["ok"] is True
    assert payload["probe"]["reached_backend"] is True


def test_fr9585_install_script_still_forwards_put():
    text = INSTALL.read_text(encoding="utf-8")
    assert 'pattern="^(GET|HEAD|POST|PUT)$"' in text
    assert "FR #9273" in text
    assert "FR #9585" in text or "Weights Save" in text


def test_fr9585_tipform_weights_save_uses_put_and_headless():
    client = CLIENT.read_text(encoding="utf-8")
    tray = TRAY.read_text(encoding="utf-8")
    weights = WEIGHTS.read_text(encoding="utf-8")
    assert 'ModelsPath = "/bob/v1/models"' in client
    assert "PUT" in client or "HttpMethod.Put" in client or '"PUT"' in client
    assert "--weights-save" in tray
    assert "weights_save" in tray or "weights_save" in weights
    # Non-2xx keeps edits (no local tray-models.json write on failure).
    assert "tray-models.json" not in weights or "no" in weights.lower()


def test_fr9585_docs_and_monitor_wired():
    docs = DIALOGS.read_text(encoding="utf-8")
    assert "PUT" in docs and "/bob/v1/models" in docs
    assert "FR #9585" in docs or "Install-BobWebhooks" in docs
    invoke = INVOKE.read_text(encoding="utf-8")
    assert "models_put_forward" in invoke
    start = START.read_text(encoding="utf-8")
    assert "`models_put_forward`" in start or "models_put_forward" in start
    assert (SCRIPTS / "Test-JeevesMonitorModelsPutForward.ps1").is_file()
    assert (MON / "models_put_forward.py").is_file()
