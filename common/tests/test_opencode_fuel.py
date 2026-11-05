"""Tests for OpenCode fuel estimation and model fallback (issue #6120)."""
from __future__ import annotations

import opencode_fuel as of


# Captured sample of real ``opencode stats --models`` output, including
# box-drawing characters and an ANSI cursor-up escape sequence.
REAL_STATS_SAMPLE = """ÔöîÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÉ
Ôöé                       OVERVIEW                         Ôöé
Ôö£ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöñ
ÔöéSessions                                             18 Ôöé
ÔöéMessages                                            361 Ôöé
ÔöéDays                                                  1 Ôöé
ÔööÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÿ

ÔöîÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÉ
Ôöé                    COST & TOKENS                       Ôöé
Ôö£ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöñ
ÔöéTotal Cost                                        $9.33 Ôöé
ÔöéAvg Cost/Day                                      $9.33 Ôöé
ÔöéAvg Tokens/Session                                 2.2M Ôöé
ÔöéMedian Tokens/Session                              7.8K Ôöé
ÔöéInput                                            798.1K Ôöé
ÔöéOutput                                            57.1K Ôöé
ÔöéCache Read                                        39.4M Ôöé
ÔöéCache Write                                           0 Ôöé
ÔööÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÿ

ÔöîÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÉ
Ôöé                      MODEL USAGE                       Ôöé
Ôö£ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöñ
Ôöé opencode-go/kimi-k2.7-code                             Ôöé
Ôöé  Messages                                          258 Ôöé
Ôöé  Input Tokens                                   447.8K Ôöé
Ôöé  Output Tokens                                   94.5K Ôöé
Ôöé  Cache Read                                      34.5M Ôöé
Ôöé  Cache Write                                         0 Ôöé
Ôöé  Cost                                          $7.3553 Ôöé
Ôö£ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöñ
Ôöé opencode-go/glm-5.3                                    Ôöé
Ôöé  Messages                                           81 Ôöé
Ôöé  Input Tokens                                   331.6K Ôöé
Ôöé  Output Tokens                                   50.1K Ôöé
Ôöé  Cache Read                                       4.9M Ôöé
Ôöé  Cache Write                                         0 Ôöé
Ôöé  Cost                                          $1.9668 Ôöé
Ôö£ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöñ
Ôöé opencode-go/longcat-2.0                                Ôöé
Ôöé  Messages                                            3 Ôöé
Ôöé  Input Tokens                                     9.3K Ôöé
Ôöé  Output Tokens                                      17 Ôöé
Ôöé  Cache Read                                          0 Ôöé
Ôöé  Cache Write                                         0 Ôöé
Ôöé  Cost                                          $0.0028 Ôöé
Ôö£ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöñ
Ôöé opencode-go/glm-5.3-flash                              Ôöé
Ôöé  Messages                                            1 Ôöé
Ôöé  Input Tokens                                     9.4K Ôöé
Ôöé  Output Tokens                                      36 Ôöé
Ôöé  Cache Read                                          0 Ôöé
Ôöé  Cache Write                                         0 Ôöé
Ôöé  Cost                                          $0.0014 Ôöé
Ôö£ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöñ
[1AÔööÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÿ

ÔöîÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÉ
Ôöé                      TOOL USAGE                        Ôöé
Ôö£ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöñ
Ôöé read               ÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûê 109 (26.0%)    Ôöé
Ôöé bash               ÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûê     94 (22.4%)    Ôöé
Ôöé grep               ÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûê       83 (19.8%)    Ôöé
Ôöé edit               ÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔûê        79 (18.9%)    Ôöé
Ôöé glob               ÔûêÔûêÔûêÔûê                  27 ( 6.4%)    Ôöé
Ôöé todowrite          ÔûêÔûê                    16 ( 3.8%)    Ôöé
Ôöé write              Ôûê                      7 ( 1.7%)    Ôöé
Ôöé websearch          Ôûê                      3 ( 0.7%)    Ôöé
Ôöé webfetch           Ôûê                      1 ( 0.2%)    Ôöé
ÔööÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÿ

"""


def test_fuel_from_stats_unknown_is_empty():
    assert of.fuel_from_stats({}) == {
        "opencode-free": None,
        "opencode-go": None,
        "models": {},
        "free_model_ids": [],
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


def test_parse_opencode_stats_json_passes_through_fixture_shape():
    doc = {"costs": {"glm-5.3": 7.5}, "free_models": ["beam-free"]}
    parsed = of.parse_opencode_stats_json(doc)
    assert parsed["costs"] == doc["costs"]
    assert parsed["free_models"] == doc["free_models"]
    assert parsed["parse_success"] is True


def test_parse_opencode_stats_json_extracts_costs_from_models_array():
    doc = {
        "schemaVersion": 1,
        "totals": {"cost": 7.5},
        "models": [
            {"id": "opencode-go/glm-5.3", "cost": 7.5, "messages": 10},
            {"name": "opencode-go/kimi-k3", "cost": 1.0},
        ],
    }
    parsed = of.parse_opencode_stats_json(doc)
    assert parsed["costs"]["glm-5.3"] == 7.5
    assert parsed["costs"]["kimi-k3"] == 1.0


def test_parse_opencode_stats_json_extracts_costs_from_model_usage_dict():
    doc = {
        "totals": {"cost": 8.5},
        "modelUsage": {
            "glm-5.3": {"cost": 8.5, "messages": 5},
            "kimi-k3": {"cost": 0.5},
        },
    }
    parsed = of.parse_opencode_stats_json(doc)
    assert parsed["costs"]["glm-5.3"] == 8.5
    assert parsed["costs"]["kimi-k3"] == 0.5


def test_parse_opencode_stats_json_extracts_free_models_from_provider():
    doc = {
        "models": [
            {"id": "opencode-free/beam-free"},
            {"id": "opencode-free/iceman-contributor-free"},
            {"id": "opencode-go/glm-5.3", "cost": 1.0},
        ]
    }
    parsed = of.parse_opencode_stats_json(doc)
    assert "beam-free" in parsed["free_models"]
    assert "iceman-contributor-free" in parsed["free_models"]


def test_parse_opencode_stats_json_extracts_free_models_from_dict_keys():
    doc = {
        "modelUsage": {
            "opencode-free/beam-free": {"cost": 0},
            "opencode-go/glm-5.3": {"cost": 1.0},
        }
    }
    parsed = of.parse_opencode_stats_json(doc)
    assert "beam-free" in parsed["free_models"]
    assert "glm-5.3" in parsed["costs"]


def test_parse_opencode_stats_json_discovers_free_models_without_usage():
    # ``opencode models`` style catalogue: free model present but no recorded cost.
    doc = {
        "models": {
            "opencode-free/beam-free": {},
            "opencode-go/glm-5.3": {"cost": 1.0},
        }
    }
    parsed = of.parse_opencode_stats_json(doc)
    assert "beam-free" in parsed["free_models"]
    assert "glm-5.3" in parsed["costs"]


def test_parse_opencode_stats_json_unknown_shape_returns_empty():
    assert of.parse_opencode_stats_json({"unexpected": []}) == {
        "costs": {},
        "free_models": [],
        "parse_success": False,
    }
    assert of.parse_opencode_stats_json(None) == {
        "costs": {},
        "free_models": [],
        "parse_success": False,
    }


def test_parse_opencode_stats_text_extracts_total_and_model_costs():
    parsed = of.parse_opencode_stats_text(REAL_STATS_SAMPLE)
    assert parsed["total_cost"] > 0
    assert "kimi-k2.7-code" in parsed["costs"]
    assert parsed["costs"]["kimi-k2.7-code"] > 0
    assert parsed["costs"]["glm-5.3"] > 0


def test_parse_opencode_stats_text_ignores_unknown_models():
    sample = """┌────────────────────────────────────────────────────────┐
│                      MODEL USAGE                       │
├────────────────────────────────────────────────────────┤
│ opencode-go/some-unknown-model                         │
│  Messages                                            1 │
│  Cost                                            $9.99 │
├────────────────────────────────────────────────────────┤
│ opencode-go/glm-5.3                                    │
│  Messages                                           10 │
│  Cost                                            $7.50 │
└────────────────────────────────────────────────────────┘
"""
    parsed = of.parse_opencode_stats_text(sample)
    assert "some-unknown-model" not in parsed["costs"]
    assert "glm-5.3" in parsed["costs"]
    assert parsed["costs"]["glm-5.3"] == 7.5


def test_parse_opencode_stats_text_strips_ansi_escape_sequences():
    parsed = of.parse_opencode_stats_text(REAL_STATS_SAMPLE)
    assert parsed["total_cost"] is not None
    assert parsed["costs"]


def test_parse_opencode_stats_text_returns_none_on_failure():
    assert of.parse_opencode_stats_text("") == {
        "costs": {},
        "free_models": [],
        "total_cost": None,
        "parse_success": False,
    }
    garbage = of.parse_opencode_stats_text("not a stats table")
    assert garbage["total_cost"] is None
    assert garbage["parse_success"] is False


def test_parse_opencode_stats_text_detects_free_models():
    sample = """┌────────────────────────────────────────────────────────┐
│                      MODEL USAGE                       │
├────────────────────────────────────────────────────────┤
│ opencode-free/beam-free                                │
│  Messages                                            5 │
│  Cost                                            $0.10 │
├────────────────────────────────────────────────────────┤
│ opencode-go/glm-5.3                                    │
│  Messages                                           10 │
│  Cost                                            $7.50 │
└────────────────────────────────────────────────────────┘
"""
    parsed = of.parse_opencode_stats_text(sample)
    assert "beam-free" in parsed["free_models"]
    assert "glm-5.3" in parsed["costs"]
    assert parsed["costs"]["glm-5.3"] == 7.5


def test_parse_opencode_stats_text_or_json_accepts_json_fixture():
    doc = '{"costs": {"glm-5.3": 3.0}, "free_models": ["beam-free"]}'
    parsed = of.parse_opencode_stats_text_or_json(doc)
    assert parsed["costs"]["glm-5.3"] == 3.0
    assert "beam-free" in parsed["free_models"]


def test_parse_opencode_stats_text_or_json_accepts_plain_text():
    sample = """┌────────────────────────────────────────────────────────┐
│                      MODEL USAGE                       │
├────────────────────────────────────────────────────────┤
│ opencode-free/beam-free                                │
│  Messages                                            5 │
│  Cost                                            $0.10 │
├────────────────────────────────────────────────────────┤
│ opencode-go/glm-5.3                                    │
│  Messages                                           10 │
│  Cost                                            $7.50 │
└────────────────────────────────────────────────────────┘
"""
    parsed = of.parse_opencode_stats_text_or_json(sample)
    assert "beam-free" in parsed["free_models"]
    assert parsed["costs"]["glm-5.3"] == 7.5


def test_parse_opencode_stats_text_or_json_returns_empty_for_garbage():
    assert of.parse_opencode_stats_text_or_json("garbage") == {
        "costs": {},
        "free_models": [],
        "parse_success": False,
    }


def test_parse_opencode_stats_json_strips_provider_prefix_from_dict_keys():
    doc = {
        "modelUsage": {
            "opencode-go/glm-5.3": {"cost": 7.5, "messages": 5},
            "opencode-go/kimi-k3": {"cost": 1.0},
        },
    }
    parsed = of.parse_opencode_stats_json(doc)
    assert parsed["costs"]["glm-5.3"] == 7.5
    assert parsed["costs"]["kimi-k3"] == 1.0


def test_fuel_from_windowed_stats_uses_most_utilised_window():
    # Monthly looks healthy, but the weekly window is exhausted.
    windowed = {
        "week": {"costs": {"glm-5.3": 8.0}, "parse_success": True},
        "month": {"costs": {"glm-5.3": 7.5}, "parse_success": True},
    }
    fuel = of.fuel_from_windowed_stats(windowed)
    # week cap = 15 * 0.50 = 7.5; cost 8.0 => 0% remaining.
    assert fuel["models"]["glm-5.3"] == 0
    assert fuel["opencode-go"] == 0


def test_fuel_from_windowed_stats_missing_window_means_unknown():
    windowed = {
        "month": {"costs": {"glm-5.3": 7.5}, "parse_success": True},
    }
    fuel = of.fuel_from_windowed_stats(windowed)
    # A failed/missing window keeps the model allowance unknown.
    assert fuel["models"].get("glm-5.3") is None
    assert fuel["opencode-go"] is None


def test_fuel_from_windowed_stats_free_when_any_window_has_free_models():
    windowed = {
        "week": {"free_models": ["beam-free"]},
        "month": {"free_models": []},
    }
    assert of.fuel_from_windowed_stats(windowed)["opencode-free"] == 100


def test_fuel_from_windowed_stats_unknown_without_data():
    assert of.fuel_from_windowed_stats({}) == {
        "opencode-free": None,
        "opencode-go": None,
        "models": {},
        "free_model_ids": [],
    }


def test_fuel_from_windowed_stats_missing_model_in_successful_window_counts_as_zero():
    # The monthly window succeeded and contains usage for glm-5.3. The weekly
    # window succeeded but contains no row for glm-5.3, so that model cost is
    # zero in that window (not unknown).
    windowed = {
        "week": {"costs": {}, "parse_success": True},
        "month": {"costs": {"glm-5.3": 7.5}, "parse_success": True},
    }
    fuel = of.fuel_from_windowed_stats(windowed)
    # Most-utilised window is month: 7.5 / 15 => 50% remaining.
    assert fuel["models"]["glm-5.3"] == 50
    assert fuel["opencode-go"] == 50


def test_fuel_from_windowed_stats_failed_window_keeps_model_unknown():
    # The weekly stats call failed/timed out, so its cost is unknown rather
    # than zero; the model allowance must stay unknown.
    windowed = {
        "week": {"costs": {}, "parse_success": False},
        "month": {"costs": {"glm-5.3": 7.5}, "parse_success": True},
    }
    fuel = of.fuel_from_windowed_stats(windowed)
    assert fuel["models"].get("glm-5.3") is None
    assert fuel["opencode-go"] is None


def test_fuel_from_windowed_stats_model_absent_from_every_window_stays_unknown():
    # A model that never appears in any successful window remains unknown;
    # a missing row alone must not be treated as zero usage.
    windowed = {
        "week": {"costs": {"kimi-k2.7-code": 5.0}, "parse_success": True},
        "month": {"costs": {"kimi-k2.7-code": 12.0}, "parse_success": True},
    }
    fuel = of.fuel_from_windowed_stats(windowed)
    assert "glm-5.3" not in fuel["models"]
    assert fuel["models"].get("glm-5.3") is None


def test_parse_opencode_stats_text_sessions_error_not_successful():
    # Error text containing "sessions" must not make a window parse as successful.
    sample = "Error: could not list sessions for provider opencode-go"
    parsed = of.parse_opencode_stats_text(sample)
    assert parsed["parse_success"] is False
    assert parsed["costs"] == {}
    assert parsed["free_models"] == []


def test_parse_opencode_models_text_extracts_free_models():
    text = (
        "opencode/beam-free\n"
        "opencode/iceman-contributor-free\n"
        "opencode-free/legacy-free\n"
        "opencode-go/glm-5.3\n"
    )
    assert of.parse_opencode_models_text(text) == [
        "beam-free",
        "iceman-contributor-free",
        "legacy-free",
    ]


def test_parse_opencode_model_ids_returns_full_ids():
    text = "opencode/beam-free\nopencode-go/glm-5.3\n"
    assert of.parse_opencode_model_ids(text) == ["opencode/beam-free"]


def test_parse_opencode_stats_text_or_json_accepts_models_list():
    text = "opencode/beam-free\nopencode-go/glm-5.3\n"
    parsed = of.parse_opencode_stats_text_or_json(text)
    assert parsed["free_models"] == ["beam-free"]
    assert parsed["costs"] == {}
    assert parsed["parse_success"] is True


# --- runtime rate-limit / rolling-cap pause logic ---------------------------------


def test_looks_like_rate_limit_detects_phrases():
    assert of.looks_like_rate_limit("HTTP 429 Too Many Requests") is True
    assert of.looks_like_rate_limit("usage balance exhausted") is True
    assert of.looks_like_rate_limit("rolling limit reached") is True
    assert of.looks_like_rate_limit("Payment Required") is True
    assert of.looks_like_rate_limit("all good here") is False


def test_parse_reset_time_retry_after_seconds():
    now = 1_000_000.0
    assert of.parse_reset_time("Retry-After: 300", now=now) == now + 300
    assert of.parse_reset_time("retry-after 120", now=now) == now + 120


def test_parse_reset_time_relative_units():
    now = 1_000_000.0
    assert of.parse_reset_time("resets in 30 minutes", now=now) == now + 30 * 60
    assert of.parse_reset_time("try again in 2 hours", now=now) == now + 2 * 3600
    assert of.parse_reset_time("resets after 45 seconds", now=now) == now + 45


def test_parse_reset_time_iso_timestamp():
    now = 1_000_000.0
    ts = "2026-11-05T12:00:00Z"
    parsed = of.parse_reset_time(f"reset-time: {ts}", now=now)
    assert parsed is not None
    assert parsed > now


def test_load_save_opencode_pauses(tmp_path):
    state_dir = tmp_path / "state"
    now = 1_000_000.0
    of.save_opencode_pauses(state_dir, {"opencode-go/glm-5.3": now + 100})
    loaded = of.load_opencode_pauses(state_dir, now=now)
    assert loaded == {"opencode-go/glm-5.3": now + 100}

    # Expired pauses are dropped.
    of.save_opencode_pauses(state_dir, {"opencode-go/glm-5.3": now - 1})
    assert of.load_opencode_pauses(state_dir, now=now) == {}


def test_record_opencode_pause_persists_default(tmp_path):
    state_dir = tmp_path / "state"
    now = 1_000_000.0
    reset = of.record_opencode_pause(
        state_dir, "opencode-go/glm-5.3", "rate limited", now=now
    )
    assert reset == now + of.DEFAULT_PAUSE_S
    assert of.is_opencode_model_paused("opencode-go/glm-5.3", state_dir, now=now) is True


def test_record_opencode_pause_uses_parsed_reset_time(tmp_path):
    state_dir = tmp_path / "state"
    now = 1_000_000.0
    reset = of.record_opencode_pause(
        state_dir, "opencode-go/glm-5.3", "Retry-After: 600", now=now
    )
    assert reset == now + 600


def test_record_opencode_pause_extends_existing_pause(tmp_path):
    state_dir = tmp_path / "state"
    now = 1_000_000.0
    of.record_opencode_pause(state_dir, "opencode-go/glm-5.3", "Retry-After: 300", now=now)
    later = now + 100
    reset = of.record_opencode_pause(
        state_dir, "opencode-go/glm-5.3", "Retry-After: 600", now=later
    )
    assert reset == later + 600


def test_is_opencode_model_paused_case_insensitive(tmp_path):
    state_dir = tmp_path / "state"
    now = 1_000_000.0
    of.record_opencode_pause(state_dir, "Opencode-Go/GLM-5.3", "rate limit", now=now)
    assert of.is_opencode_model_paused("opencode-go/glm-5.3", state_dir, now=now) is True
    assert of.is_opencode_model_paused("opencode-go/glm-5.3", state_dir, now=now + of.DEFAULT_PAUSE_S + 1) is False
