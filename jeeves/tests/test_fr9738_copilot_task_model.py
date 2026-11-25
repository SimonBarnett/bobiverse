"""FR #9738: build_task_body passes CCA model / base_ref from env/settings."""
from __future__ import annotations

import json
from pathlib import Path

import copilot_dispatch as cd
import jeeves_settings as js

REPO = "SimonBarnett/bobiverse"


def _row(task="FR", num=10, **extra):
    row = {
        "repo": REPO,
        "task": task,
        "id": f"#{num}",
        "url": f"https://github.com/{REPO}/issues/{num}",
        "title": "do the thing",
    }
    row.update(extra)
    return row


def test_fr9738_model_omitted_when_unset(monkeypatch):
    monkeypatch.delenv("BOB_COPILOT_MODEL", raising=False)
    monkeypatch.delenv("BOB_COPILOT_BASE_REF", raising=False)
    body = cd.build_task_body(_row())
    assert "prompt" in body
    assert "model" not in body
    assert body.get("base_ref") == "main"


def test_fr9738_model_from_env(monkeypatch):
    monkeypatch.setenv("BOB_COPILOT_MODEL", "claude-haiku-4.5")
    monkeypatch.delenv("BOB_COPILOT_BASE_REF", raising=False)
    body = cd.build_task_body(_row())
    assert body["model"] == "claude-haiku-4.5"
    assert body["base_ref"] == "main"


def test_fr9738_allowance_model_ignored_when_home_set_empty_weights(tmp_path, monkeypatch):
    """FR #9749: with home, Weights is locked; empty Copilot omits even if allowance set."""
    monkeypatch.delenv("BOB_COPILOT_MODEL", raising=False)
    monkeypatch.delenv("BOB_COPILOT_BASE_REF", raising=False)
    (tmp_path / cd.ALLOWANCE_NAME).write_text(
        json.dumps({"remaining": 3, "model": "claude-haiku-4.5", "base_ref": "develop"}),
        encoding="utf-8",
    )
    body = cd.build_task_body(_row(), home=tmp_path)
    assert "model" not in body
    assert body["base_ref"] == "develop"


def test_fr9738_env_ignored_when_home_set_empty_weights(tmp_path, monkeypatch):
    """FR #9749: home present → Weights empty wins over env (locked picker)."""
    monkeypatch.setenv("BOB_COPILOT_MODEL", "claude-haiku-4.5")
    (tmp_path / cd.ALLOWANCE_NAME).write_text(
        json.dumps({"model": "sweagent-capi:gpt-6-luna"}),
        encoding="utf-8",
    )
    body = cd.build_task_body(_row(), home=tmp_path)
    assert "model" not in body


def test_fr9738_empty_base_ref_env_omits_field(monkeypatch):
    monkeypatch.delenv("BOB_COPILOT_MODEL", raising=False)
    monkeypatch.setenv("BOB_COPILOT_BASE_REF", "")
    body = cd.build_task_body(_row())
    assert "base_ref" not in body


def test_fr9738_explicit_kwargs_override_env(monkeypatch):
    monkeypatch.setenv("BOB_COPILOT_MODEL", "env-model")
    monkeypatch.setenv("BOB_COPILOT_BASE_REF", "env-ref")
    body = cd.build_task_body(_row(), model="kw-model", base_ref="kw-ref")
    assert body["model"] == "kw-model"
    assert body["base_ref"] == "kw-ref"
    body2 = cd.build_task_body(_row(), model="", base_ref="")
    assert "model" not in body2
    assert "base_ref" not in body2


def test_fr9738_schema_keys_in_fuel_group():
    by_key = {s.key: s for s in js.SCHEMA}
    assert "BOB_COPILOT_MODEL" in by_key
    assert by_key["BOB_COPILOT_MODEL"].group == "fuel"
    assert by_key["BOB_COPILOT_BASE_REF"].group == "fuel"
    assert by_key["BOB_COPILOT_BASE_REF"].default == "main"
