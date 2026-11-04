"""Tests for OpenCode fuel estimation and model fallback (issue #6120)."""
from __future__ import annotations

import opencode_fuel as of


def test_fuel_from_stats_unknown_is_empty():
    assert of.fuel_from_stats({}) == {
        "opencode-free": None,
        "opencode-go": None,
        "models": {},
    }


def test_fuel_from_stats_computes_remaining_pct():
    stats = {"costs": {"glm-5.3": 7.5, "kimi-k2.7-code": 30.0}, "free_models": ["beam-free"]}
    fuel = of.fuel_from_stats(stats)
    assert fuel["opencode-go"] == 50  # max remaining across models
    assert fuel["models"]["glm-5.3"] == 50
    assert fuel["models"]["kimi-k2.7-code"] == 50
    assert fuel["opencode-free"] == 100


def test_fuel_from_stats_clamps_exhausted():
    stats = {"costs": {"glm-5.3": 20.0, "kimi-k2.7-code": 120.0}}
    fuel = of.fuel_from_stats(stats)
    assert fuel["models"]["glm-5.3"] == 0
    assert fuel["models"]["kimi-k2.7-code"] == 0
    assert fuel["opencode-go"] == 0


def test_fuel_from_stats_ignores_unknown_models():
    stats = {"costs": {"unknown-model": 5.0}}
    assert of.fuel_from_stats(stats)["opencode-go"] is None


def test_select_model_stays_on_preferred_when_available():
    stats = {"costs": {"glm-5.3": 1.0, "kimi-k2.7-code": 1.0}}
    assert of.select_model("glm-5.3", stats) == "glm-5.3"
    assert of.select_model("opencode-go/glm-5.3", stats) == "glm-5.3"


def test_select_model_falls_back_to_best_remaining():
    stats = {"costs": {"glm-5.3": 15.0, "kimi-k2.7-code": 1.0}}
    assert of.model_remaining_pct("glm-5.3", stats) == 0
    assert of.select_model("glm-5.3", stats) == "kimi-k2.7-code"


def test_select_model_falls_back_to_free_then_none():
    stats = {"costs": {"glm-5.3": 15.0, "kimi-k2.7-code": 60.0}, "free_models": []}
    assert of.select_model("glm-5.3", stats) is None


def test_select_model_free_when_no_go_costs():
    assert of.select_model("glm-5.3", {}) is None


def test_select_model_free_when_explicitly_available():
    assert of.select_model("glm-5.3", {"free_models": ["beam-free"]}) == "beam-free"


def test_model_is_capped_true_when_unknown():
    assert of.model_is_capped("glm-5.3", {}) is True
    assert of.model_is_capped("unknown-model", {"costs": {"glm-5.3": 1.0}}) is True


def test_model_is_capped_true_when_exhausted():
    assert of.model_is_capped("glm-5.3", {"costs": {"glm-5.3": 15.0}}) is True


def test_is_exhausted():
    assert of.is_exhausted(None) is True
    assert of.is_exhausted({"costs": {"glm-5.3": 15.0}}) is True
    assert of.is_exhausted({"costs": {"glm-5.3": 1.0}}) is False
