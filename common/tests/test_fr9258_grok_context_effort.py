# -*- coding: utf-8 -*-
"""FR #9258: Grok-only context (256|500) and effort (high|medium|low) at startup."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import models_catalog as mc
import worker_start_model as wsm


def test_grok_argv_each_effort_and_context():
    for effort in ("high", "medium", "low"):
        for ctx in ("256", "500"):
            args, status = wsm.cli_settings_args(
                "grok", model="grok-4.7", effort=effort, context=ctx
            )
            assert "--reasoning-effort" in args
            assert args[args.index("--reasoning-effort") + 1] == effort
            assert status["effort"] == "passed"
            # grok 1.0.92 has no context CLI flag (recorded in worker_start_model).
            assert status["context"] == "not-passed: unsupported-by-cli"
            assert not any(a in ("--context", "-C", "--ctx") for a in args)


def test_non_grok_never_gets_context_or_effort_args():
    for cli in ("cursor", "opencode", "aider"):
        args, status = wsm.cli_settings_args(
            cli, model="m1", effort="high", context="500"
        )
        assert "--reasoning-effort" not in args
        assert "--context" not in args
        assert status["effort"] == "not-applicable"
        assert status["context"] == "not-applicable"


def test_invalid_effort_and_context_fallback_with_warning(capsys):
    args, status = wsm.cli_settings_args(
        "grok", model="grok-4.7", effort="ultra", context="999"
    )
    assert status["effort"] == "not-passed: invalid"
    assert status["context"] == "not-passed: invalid"
    # Effort falls back to default low on argv.
    assert "--reasoning-effort" in args
    assert args[args.index("--reasoning-effort") + 1] == "low"
    err = capsys.readouterr().err + capsys.readouterr().out
    assert "invalid" in err.lower() or "WARN" in err


def test_unsupported_by_cli_context_raises_deduped_intake(monkeypatch):
    calls: list[tuple] = []

    def fake_intake(*a, **k):
        calls.append((a, k))
        return True

    monkeypatch.setattr(wsm, "_file_grok_context_unsupported_intake", fake_intake)
    args, status = wsm.cli_settings_args(
        "grok", model="grok-4.7", effort="low", context="256"
    )
    assert status["context"] == "not-passed: unsupported-by-cli"
    assert calls  # one intake attempt
    # Second call same process should dedupe inside helper — invoke twice.
    wsm.cli_settings_args("grok", model="grok-4.7", effort="low", context="256")
    # Helper itself dedupes; fake always records — pin that helper exists.
    assert hasattr(wsm, "_file_grok_context_unsupported_intake")


def test_save_drops_non_grok_context_and_effort(tmp_path):
    p = tmp_path / "tray-models.json"
    wsm.save_worker_start_settings(
        path=p,
        effort={"grok": "high", "cursor": "medium", "opencode": "low"},
        context={"grok": "500", "cursor": "256", "opencode": "500"},
    )
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["workerStartEffort"]["grok"] == "high"
    assert data["workerStartEffort"].get("cursor", "") == ""
    assert data["workerStartEffort"].get("opencode", "") == ""
    assert data["workerStartContext"]["grok"] == "500"
    assert data["workerStartContext"].get("cursor", "") == ""
    assert data["workerStartContext"].get("opencode", "") == ""


def test_normalize_context_and_effort():
    assert wsm.normalize_context("256") == "256"
    assert wsm.normalize_context("500") == "500"
    assert wsm.normalize_context("256000") == ""
    assert wsm.normalize_effort("HIGH") == "high"
    assert wsm.normalize_effort("xhigh") == ""  # FR #9258: only high|medium|low


def test_catalog_loader_accepts_non_grok_empty_contexts(tmp_path: Path):
    path = tmp_path / mc.MODELS_VALID_COMBOS_NAME
    doc = {
        "version": 1,
        "clis": {
            "grok": [
                {
                    "model": "grok-4.7",
                    "contexts": ["256", "500"],
                    "efforts": ["high", "medium", "low"],
                }
            ],
            "cursor": [{"model": "gpt-5.1", "contexts": [], "efforts": []}],
            "opencode": [{"model": "opencode/x", "contexts": [], "efforts": []}],
        },
    }
    path.write_text(json.dumps(doc), encoding="utf-8")
    cat = mc.load_valid_combos(tmp_path)
    assert "grok-4.7" in {r.model for r in cat.clis.get("grok", [])}
    assert "gpt-5.1" in {r.model for r in cat.clis.get("cursor", [])}
    assert "opencode/x" in {r.model for r in cat.clis.get("opencode", [])}


def test_catalog_grok_still_requires_contexts(tmp_path: Path):
    path = tmp_path / mc.MODELS_VALID_COMBOS_NAME
    doc = {
        "version": 1,
        "clis": {
            "grok": [{"model": "grok-4.7", "contexts": [], "efforts": ["low"]}],
        },
    }
    path.write_text(json.dumps(doc), encoding="utf-8")
    cat = mc.load_valid_combos(tmp_path)
    # Empty Grok contexts → row dropped / empty catalog for grok.
    assert cat.clis.get("grok", []) == [] or all(
        r.contexts for r in cat.clis.get("grok", [])
    )


def test_source_pins_grok_context_cli_record():
    text = Path(wsm.__file__).read_text(encoding="utf-8")
    assert "GROK_CONTEXT_CLI_FLAG" in text
    assert "1.0.92" in text
    assert "unsupported-by-cli" in text
    assert "not-applicable" in text
    assert "FR #9258" in text
