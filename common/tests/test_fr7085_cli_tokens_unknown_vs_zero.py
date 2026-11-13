"""FR #7085: every CLI stamps measured tokens or tokens=unknown; never 0/0/0."""
from __future__ import annotations

import json
from pathlib import Path

import done_usage


EXAMPLE_GROK_ZERO = (
    "DONE MRB SimonBarnett/bobiverse#6990 PASS "
    "https://github.com/SimonBarnett/bobiverse/pull/6990 "
    "model=xai/grok-4.5-build tokens_in=0 tokens_out=0 tokens_cached=0 "
    "worker_build=eccea333227f"
)


def test_fr7085_example_grok_000_is_not_measured():
    u = done_usage.parse_done_usage(EXAMPLE_GROK_ZERO)
    assert u["tokens_unknown"] is True
    assert u["tokens_in"] is None
    assert u["model"] == "xai/grok-4.5-build"
    suffix = done_usage.format_done_usage_suffix(
        {
            "model": "xai/grok-4.5-build",
            "tokens_in": 0,
            "tokens_out": 0,
            "tokens_cached": 0,
            "tokens_unknown": False,
        },
        worker_build="eccea333227f",
    )
    assert "tokens=unknown" in suffix
    assert "tokens_in=0" not in suffix


def test_fr7085_grok_fixture_measured(tmp_path: Path):
    p = tmp_path / "usage.json"
    p.write_text(
        json.dumps(
            {
                "session": {
                    "modelUsage": {
                        "grok-4.5-build": {
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
    u = done_usage.measure_seat_usage("grok", grok_usage_path=p)
    assert u["tokens_unknown"] is False
    assert u["tokens_in"] == 100
    assert u["tokens_out"] == 20
    assert u["tokens_cached"] == 5
    stamp = done_usage.format_done_usage_suffix(u)
    assert "tokens_in=100" in stamp


def test_fr7085_grok_all_zero_is_unknown(tmp_path: Path):
    p = tmp_path / "usage.json"
    p.write_text(
        json.dumps(
            {
                "session": {
                    "primaryModelId": "grok-4.5-build",
                    "inputTokens": 0,
                    "outputTokens": 0,
                    "cachedReadTokens": 0,
                    "modelUsage": {
                        "grok-4.5-build": {
                            "inputTokens": 0,
                            "outputTokens": 0,
                            "cachedReadTokens": 0,
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    u = done_usage.measure_seat_usage("grok", grok_usage_path=p)
    assert u["tokens_unknown"] is True
    stamp = done_usage.format_done_usage_suffix(u, worker_build="abc")
    assert "tokens=unknown" in stamp
    assert "tokens_in=" not in stamp


def test_fr7085_cursor_fixture_measured(tmp_path: Path):
    p = tmp_path / "cursor-usage.json"
    p.write_text(
        json.dumps({"model": "composer-2", "tokens_in": 11, "tokens_out": 3, "tokens_cached": 1}),
        encoding="utf-8",
    )
    u = done_usage.measure_seat_usage("cursor", cursor_usage_path=p)
    assert u["tokens_in"] == 11
    assert "tokens_in=11" in done_usage.format_done_usage_suffix(u)


def test_fr7085_cursor_zero_is_unknown(tmp_path: Path):
    p = tmp_path / "cursor-usage.json"
    p.write_text(
        json.dumps({"model": "composer-2", "tokens_in": 0, "tokens_out": 0, "tokens_cached": 0}),
        encoding="utf-8",
    )
    u = done_usage.measure_seat_usage("cursor", cursor_usage_path=p)
    assert u["tokens_unknown"] is True
    assert "tokens=unknown" in done_usage.format_done_usage_suffix(u)
    assert "tokens_in=0" not in done_usage.format_done_usage_suffix(u)


def test_fr7085_aider_fixture_measured(tmp_path: Path):
    p = tmp_path / "aider-usage.json"
    p.write_text(
        json.dumps({"model": "gpt-4o", "tokens_in": 40, "tokens_out": 8, "tokens_cached": 2}),
        encoding="utf-8",
    )
    u = done_usage.measure_seat_usage("aider", aider_usage_path=p)
    assert u["tokens_in"] == 40
    assert "tokens_in=40" in done_usage.format_done_usage_suffix(u)


def test_fr7085_aider_missing_is_unknown(tmp_path: Path):
    u = done_usage.measure_seat_usage("aider", aider_usage_path=tmp_path / "missing.json")
    assert u["tokens_unknown"] is True
    assert "tokens=unknown" in done_usage.format_done_usage_suffix(u)


def test_fr7085_opencode_fixture_measured(tmp_path: Path):
    p = tmp_path / "opencode-usage.json"
    p.write_text(
        json.dumps({"model": "opencode-go", "tokens_in": 7, "tokens_out": 2, "tokens_cached": 0}),
        encoding="utf-8",
    )
    u = done_usage.measure_seat_usage("opencode", opencode_usage_path=p)
    assert u["tokens_in"] == 7
    stamp = done_usage.format_done_usage_suffix(u)
    assert "tokens_in=7" in stamp
    assert "tokens_cached=0" in stamp


def test_fr7085_delta_all_zero_is_unknown():
    base = {
        "model": "xai/grok-4.5-build",
        "tokens_in": 10,
        "tokens_out": 2,
        "tokens_cached": 1,
        "tokens_unknown": False,
    }
    cur = dict(base)
    d = done_usage.usage_delta(base, cur)
    assert d["tokens_unknown"] is True
    assert "tokens=unknown" in done_usage.format_done_usage_suffix(d)
    assert "tokens_in=0" not in done_usage.format_done_usage_suffix(d)
