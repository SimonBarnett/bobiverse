"""BOB-15 / FR #8711: webhook start-contract settings reach CLI dry-run args."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import models_webhook as mw  # noqa: E402
import worker_start_model as wsm  # noqa: E402


AGENTS_DOC = {
    "agents": [
        {"agent": "Grok", "cli": "Grok", "model": "grok-4.7", "context": "256000", "effort": "low"},
        {"agent": "Cursor", "cli": "Cursor", "model": "gpt-5", "context": "", "effort": ""},
        {"agent": "Opencode", "cli": "Opencode", "model": "opencode-go/deepseek-v4-pro", "context": "default", "effort": ""},
        {"agent": "Opencode-Free", "cli": "Opencode", "model": "opencode/deepseek-v4.1-flash-free", "context": "default", "effort": ""},
        {"agent": "Plan", "cli": "Grok", "model": "build0.1", "context": "", "effort": "medium"},
    ]
}


class _Resp:
    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_fetch_models_webhook_valid_and_cache(monkeypatch):
    mw.clear_models_webhook_cache()
    calls = {"n": 0}

    def fake_open(req, timeout=0):
        calls["n"] += 1
        return _Resp(json.dumps(AGENTS_DOC).encode("utf-8"))

    monkeypatch.setattr(mw.urllib.request, "urlopen", fake_open)
    doc = mw.fetch_models_webhook(url="http://127.0.0.1/models", force=True)
    assert doc is not None
    assert len(doc["agents"]) >= 4
    row = mw.lookup_webhook_row("grok", doc=doc)
    assert row["model"] == "grok-4.7"
    mw.fetch_models_webhook(url="http://127.0.0.1/models")
    assert calls["n"] == 1  # cached


def test_fetch_models_webhook_failures(monkeypatch):
    mw.clear_models_webhook_cache()

    def boom(req, timeout=0):
        raise mw.urllib.error.HTTPError("http://x", 404, "no", hdrs=None, fp=None)

    monkeypatch.setattr(mw.urllib.request, "urlopen", boom)
    assert mw.fetch_models_webhook(url="http://127.0.0.1/missing", force=True) is None

    def empty(req, timeout=0):
        return _Resp(b"")

    monkeypatch.setattr(mw.urllib.request, "urlopen", empty)
    mw.clear_models_webhook_cache()
    assert mw.fetch_models_webhook(url="http://127.0.0.1/empty", force=True) is None


def test_normalize_rejects_metachar_model_and_invalid_effort():
    row, reasons = mw.normalize_agent_row(
        {"agent": "Grok", "cli": "Grok", "model": "bad;rm", "context": "nope", "effort": "nope"},
        valid_contexts={"256000"},
        valid_efforts={"low", "high"},
    )
    assert row is not None
    assert row["model"] == ""
    assert reasons.get("model") == "model_metachar"
    assert row["context"] == ""
    assert row["effort"] == ""


def test_webhook_overrides_tray_env_pin_wins(tmp_path, monkeypatch):
    mw.clear_models_webhook_cache()
    tray = tmp_path / "Bobiverse" / "tray-models.json"
    tray.parent.mkdir(parents=True)
    tray.write_text(
        json.dumps({"workerStartModels": {"grok": "tray-model"}, "workerStartEffort": {"grok": "high"}}),
        encoding="utf-8",
    )

    def fake_open(req, timeout=0):
        return _Resp(json.dumps(AGENTS_DOC).encode("utf-8"))

    monkeypatch.setattr(mw.urllib.request, "urlopen", fake_open)
    env = {
        "LOCALAPPDATA": str(tmp_path),
        "BOB_MODELS_WEBHOOK_URL": "http://127.0.0.1/models",
    }
    cfg = wsm.load_worker_start_config(env=env)
    assert cfg["workerStartModels"]["grok"] == "grok-4.7"
    assert cfg["settings_source"]["grok"] == "webhook"

    env2 = dict(env)
    env2["BOB_GROK_MODEL"] = "pinned-model"
    cfg2 = wsm.load_worker_start_config(env=env2)
    assert wsm.launch_selected_model("grok", cfg2, env2) == "pinned-model"
    assert cfg2["settings_source"]["grok"] == "env-pin"


def test_cli_settings_args_grok_cursor_context_unsupported():
    # FR #9258: 256000 is invalid (allowed are 256|500) → not-passed: invalid.
    args, st = wsm.cli_settings_args("grok", model="grok-4.7", effort="low", context="256000")
    assert args == ["--model", "grok-4.7", "--reasoning-effort", "low"]
    assert st["model"] == "passed"
    assert st["context"] == "not-passed: invalid"
    # Valid Grok context with no CLI flag → unsupported-by-cli (seat still starts).
    args2, st2 = wsm.cli_settings_args("grok", model="grok-4.7", effort="low", context="256")
    assert "--reasoning-effort" in args2
    assert st2["context"] == "not-passed: unsupported-by-cli"
    # Non-Grok: context/effort are not-applicable (never unsupported).
    cargs, cst = wsm.cli_settings_args("cursor", model="gpt-5", effort="high")
    assert cargs == ["--model", "gpt-5"]
    assert cst["effort"] == "not-applicable"
    assert cst["context"] == "not-applicable"


def test_append_launch_dryrun_contains_model_args(tmp_path):
    path = tmp_path / "launch-dryrun.jsonl"
    args, st = wsm.cli_settings_args("grok", model="grok-4.7", effort="medium")
    wsm.append_launch_dryrun(
        {
            "kind": "grok",
            "mode": "agent",
            "settings_source": "webhook",
            "model": "grok-4.7",
            "effort": "medium",
            "context": "256000",
            "setting_status": st,
            "cli_args": ["C:/fake/grok.exe"] + args,
            "executable": "C:/fake/grok.exe",
        },
        path=path,
    )
    line = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert line["model"] == "grok-4.7"
    assert "--model" in line["cli_args"]
    assert "grok-4.7" in line["cli_args"]
    assert line["settings_source"] == "webhook"


def test_write_launch_record_includes_context_and_source(tmp_path):
    dest = wsm.write_launch_record(
        tmp_path,
        kind="grok",
        model="grok-4.7",
        effort="low",
        argv=["grok", "--model", "grok-4.7"],
        context="256000",
        settings_source="webhook",
        cli_settings_args=["--model", "grok-4.7", "--reasoning-effort", "low"],
        setting_status={"model": "passed"},
    )
    rec = json.loads(dest.read_text(encoding="utf-8"))
    assert rec["context"] == "256000"
    assert rec["settings_source"] == "webhook"
    assert rec["cli_settings_args"][0] == "--model"


def test_build_bob_worker_hidden_import_models_webhook():
    root = Path(__file__).resolve().parents[2]
    ps1 = (root / "bob" / "scripts" / "Build-BobWorker.ps1").read_text(encoding="utf-8")
    assert "models_webhook" in ps1
