"""MRB #6808: modelUsage at doc root; slash model id; stamp parse matches ledger fields."""
from __future__ import annotations

import json
from pathlib import Path

import done_usage


def test_mrb6808_model_usage_on_document_root(tmp_path: Path):
    path = tmp_path / "usage.json"
    path.write_text(
        json.dumps(
            {
                "primaryModelId": "other-primary",
                "inputTokens": 1,
                "outputTokens": 1,
                "modelUsage": {
                    "grok-4.5-build": {
                        "inputTokens": 100,
                        "outputTokens": 20,
                        "cachedReadTokens": 5,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    u = done_usage.read_grok_usage(path)
    assert u["model"] == "xai/grok-4.5-build"
    assert u["tokens_in"] == 100


def test_mrb6808_model_key_with_slash_not_double_prefixed(tmp_path: Path):
    path = tmp_path / "usage.json"
    path.write_text(
        json.dumps(
            {
                "session": {
                    "modelUsage": {
                        "xai/grok-4.5-build": {
                            "inputTokens": 100,
                            "outputTokens": 20,
                            "cachedReadTokens": 5,
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    u = done_usage.read_grok_usage(path)
    assert u["model"] == "xai/grok-4.5-build"
    stamp = done_usage.format_done_usage_suffix(u, worker_build="t")
    parsed = done_usage.parse_done_usage(stamp)
    assert parsed["tokens_in"] == 100
    assert parsed["tokens_out"] == 20
    assert parsed["tokens_cached"] == 5
    assert parsed["model"] == "xai/grok-4.5-build"
    assert parsed["tokens_unknown"] is False
