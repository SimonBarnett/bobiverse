"""FR #7833: a literal $model start_model is unknown, not a mismatch."""
from __future__ import annotations

import worker_start_model as wsm

CFG = {
    "workerModelCostTiers": {
        "opencode/deepseek-v4.1-flash-free": "min",
        "EXAMPLE_GROK_MAX": "max",
        "EXAMPLE_GROK_MIN": "min",
    },
    "jobRequiredModelTier": {"FR": "min", "MRB": "medium"},
}


def setup_function():
    wsm._placeholder_reported.clear()


def test_fr7833_placeholder_with_configured_model_uses_that_tier():
    reports: list[tuple[str, str]] = []
    fields = {
        "start_model": "$model",
        "configured_model": "opencode/deepseek-v4.1-flash-free",
        "model_mismatch": True,
        "cost_tier": "max",
    }
    allowed = wsm.seat_model_allows(
        fields, "FR", CFG, nick="redqueen-13968", report=lambda n, v: reports.append((n, v))
    )
    assert allowed is True
    assert reports == [("redqueen-13968", "$model")]
    again = wsm.seat_model_allows(
        fields, "FR", CFG, nick="redqueen-13968", report=lambda n, v: reports.append((n, v))
    )
    assert again is True
    assert len(reports) == 1
    normalized, note = wsm.normalize_placeholder_start_model(fields, CFG)
    assert note == "$model"
    assert normalized["model_mismatch"] is False
    assert normalized["start_model"] == "opencode/deepseek-v4.1-flash-free"
    assert normalized["cost_tier"] == "min"


def test_fr7833_placeholder_without_configured_matches_no_model():
    reports: list[tuple[str, str]] = []
    fields = {"start_model": "${model}", "model_mismatch": True}
    bare = wsm.seat_model_allows({}, "MRB", CFG, nick="marchhare-1")
    held = wsm.seat_model_allows(
        fields, "MRB", CFG, nick="marchhare-28996", report=lambda n, v: reports.append((n, v))
    )
    assert bare is True
    assert held is True
    assert reports == [("marchhare-28996", "${model}")]


def test_fr7833_real_mismatch_still_refused():
    reports: list[tuple[str, str]] = []
    fields = {
        "start_model": "EXAMPLE_GROK_MIN",
        "configured_model": "EXAMPLE_GROK_MAX",
        "model_mismatch": True,
        "cost_tier": "min",
    }
    allowed = wsm.seat_model_allows(
        fields, "FR", CFG, nick="redqueen-9", report=lambda n, v: reports.append((n, v))
    )
    assert allowed is False
    assert reports == []
