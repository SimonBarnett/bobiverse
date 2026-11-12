"""FR #6781: Grok usage.json modelUsage wins over primaryModelId on DONE stamp."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import done_usage  # noqa: E402


def _write(tmp_path: Path, doc: dict) -> Path:
    path = tmp_path / "usage.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_read_grok_usage_single_model_usage_wins_over_primary(tmp_path: Path):
    """S1 / FR-001: one modelUsage entry supplies model + tokens; primaryModelId loses."""
    path = _write(
        tmp_path,
        {
            "session": {
                "inputTokens": 999,
                "outputTokens": 99,
                "cachedReadTokens": 88,
                "primaryModelId": "other-primary",
                "modelUsage": {
                    "grok-4.5-build": {
                        "inputTokens": 100,
                        "outputTokens": 20,
                        "cachedReadTokens": 5,
                    }
                },
            }
        },
    )
    u = done_usage.read_grok_usage(path)
    assert u["tokens_unknown"] is False
    assert u["tokens_in"] == 100
    assert u["tokens_out"] == 20
    assert u["tokens_cached"] == 5
    assert u["model"] == "xai/grok-4.5-build"


def test_read_grok_usage_multi_model_usage_stays_unknown(tmp_path: Path):
    path = _write(
        tmp_path,
        {
            "session": {
                "inputTokens": 100,
                "outputTokens": 20,
                "cachedReadTokens": 5,
                "primaryModelId": "grok-4.5-build",
                "modelUsage": {
                    "grok-4.5-build": {
                        "inputTokens": 60,
                        "outputTokens": 10,
                        "cachedReadTokens": 2,
                    },
                    "grok-code-fast-1": {
                        "inputTokens": 40,
                        "outputTokens": 10,
                        "cachedReadTokens": 3,
                    },
                },
            }
        },
    )
    u = done_usage.read_grok_usage(path)
    assert u["tokens_unknown"] is True
    assert u["tokens_in"] is None
    assert u["tokens_out"] is None


def test_measure_seat_usage_grok_model_usage_fixture(tmp_path: Path):
    path = _write(
        tmp_path,
        {
            "session": {
                "primaryModelId": "wrong-id",
                "inputTokens": 1,
                "outputTokens": 1,
                "cachedReadTokens": 1,
                "modelUsage": {
                    "grok-4.5-build": {
                        "inputTokens": 100,
                        "outputTokens": 20,
                        "cachedReadTokens": 5,
                    }
                },
            }
        },
    )
    u = done_usage.measure_seat_usage("grok", grok_usage_path=path)
    stamp = done_usage.format_done_usage_suffix(u, worker_build="test")
    assert "tokens_in=100" in stamp
    assert "tokens_out=20" in stamp
    assert "tokens_cached=5" in stamp
    assert "model=xai/grok-4.5-build" in stamp
    assert "tokens=unknown" not in stamp


def test_measure_seat_usage_grok_missing_still_unknown(tmp_path: Path):
    u = done_usage.measure_seat_usage("grok", grok_usage_path=tmp_path / "missing.json")
    assert u["tokens_unknown"] is True
    stamp = done_usage.format_done_usage_suffix(u, worker_build="test")
    assert "tokens=unknown" in stamp
