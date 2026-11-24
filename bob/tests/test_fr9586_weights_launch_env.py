# -*- coding: utf-8 -*-
"""FR #9586: seat start applies Model/Context/Effort from GET /bob/v1/models."""
from __future__ import annotations

import subprocess

import worker_start_model as wsm
from repo_layout import REPO

TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
CLIENT = REPO / "bob" / "tray" / "dialogs" / "BobModelsClient.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
WEBHOOK = REPO / "bob" / "tray" / "src" / "Private" / "Get-BobModelsWebhook.ps1"
FIXTURE_GROK = REPO / "bob" / "tests" / "fixtures" / "models-catalog-grok.json"


def test_fr9586_bob_models_client_resolve_launch_row():
    cs = CLIENT.read_text(encoding="utf-8-sig")
    assert "ResolveAgentLaunchRow" in cs
    assert "FindAgentRow" in cs
    assert "BOB_MODELS_CATALOG" in cs
    assert "/bob/v1/models" in cs or "ResolveUrl" in cs


def test_fr9586_tipform_logs_source_models_webhook_and_refuses_empty_grok():
    cs = TRAY.read_text(encoding="utf-8-sig")
    assert 'source",' in cs or '"models-webhook"' in cs
    assert "models-webhook" in cs
    assert "ApplyWeightsLaunchEnv" in cs
    assert 'env["BOB_GROK_EFFORT"]' in cs
    assert 'env["BOB_WORKER_START_EFFORT"]' in cs
    assert 'env["BOB_GROK_CONTEXT"]' in cs
    assert "weights-model-missing" in cs
    assert "Weights has no Grok model" in cs


def test_fr9586_watch_passes_effort_context_session_env():
    ps = WATCH.read_text(encoding="utf-8-sig")
    assert "Resolve-BobTrayWeightsAgentRow" in ps
    assert "Get-BobTrayWeightsLaunchField" in ps
    assert "Get-BobModelsWebhookAgentRow" in ps
    assert "[string]$Effort" in ps
    assert "[string]$Context" in ps
    assert "BOB_WORKER_START_EFFORT" in ps
    assert "BOB_GROK_EFFORT" in ps
    assert "BOB_WORKER_START_CONTEXT" in ps
    assert "source=models-webhook" in ps
    assert "weights-model-missing" in ps


def test_fr9586_worker_env_effort_context_wins_over_tray_models():
    """Child env from Weights GET wins; settings_source becomes models-webhook."""
    cfg = {
        "workerStartEffort": {"grok": "low"},
        "workerStartContext": {"grok": "256"},
        "settings_source": {"grok": "local"},
    }
    env = {
        "BOB_GROK_EFFORT": "high",
        "BOB_GROK_CONTEXT": "500",
        "BOB_GROK_MODEL": "grok-4",
    }
    assert wsm.configured_start_effort("grok", cfg, env=env) == "high"
    assert wsm.configured_start_context("grok", cfg, env=env) == "500"
    resolved = wsm.resolved_start_settings("grok", cfg=cfg, env=env)
    assert resolved["effort"] == "high"
    assert resolved["context"] == "500"
    assert resolved["settings_source"] == "models-webhook"


def test_fr9586_worker_env_aliases_bob_worker_start_keys():
    cfg = {"workerStartEffort": {"grok": "low"}, "workerStartContext": {"grok": "256"}}
    env = {
        "BOB_WORKER_START_EFFORT": "medium",
        "BOB_WORKER_START_CONTEXT": "500",
    }
    assert wsm.configured_start_effort("grok", cfg, env=env) == "medium"
    assert wsm.configured_start_context("grok", cfg, env=env) == "500"


def test_fr9586_fixture_matrix_model_context_effort():
    script = (
        ". '%s'\n"
        "$row = Get-BobModelsWebhookAgentRow -AgentId 'Grok' -FixturePath '%s'\n"
        "Write-Output (('model={0};context={1};effort={2}' -f "
        "[string]$row.model, [string]$row.context, [string]$row.effort))\n"
    ) % (
        str(WEBHOOK).replace("'", "''"),
        str(FIXTURE_GROK).replace("'", "''"),
    )
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "model=grok-4;context=200k;effort=high"
