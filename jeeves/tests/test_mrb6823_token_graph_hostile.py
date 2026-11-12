"""MRB #6823 hostile pins: FR-003 summary wins; /api/pools has no token fields."""
from __future__ import annotations

import json
from pathlib import Path

import jeeves_settings as js
import jeeves_settings_http as http


def test_mrb6823_prefers_summary_by_model(tmp_path: Path):
    digest = tmp_path / "digest"
    digest.mkdir()
    payload = {
        "rows": [
            {
                "model": "should-not-appear",
                "tokens_in": 999,
                "tokens_out": 999,
                "tokens_unknown": False,
            }
        ],
        "summary": {
            "unknown_jobs": 2,
            "by_model": [
                {
                    "model": "xai/grok-4.7",
                    "measured_jobs": 1,
                    "tokens_in": 10,
                    "tokens_out": 5,
                    "tokens_cached": 1,
                }
            ],
        },
    }
    (digest / "job-cost-ledger.json").write_text(json.dumps(payload), encoding="utf-8")
    g = http.load_status_token_graph(digest)
    html = http._render_token_graph_html(g)
    assert "xai/grok-4.7" in html
    assert "should-not-appear" not in html
    assert "unknown_jobs: 2" in html


def test_mrb6823_api_pools_payload_has_no_token_keys(tmp_path: Path):
    home = tmp_path / "chair"
    home.mkdir()
    digest = tmp_path / "digest"
    digest.mkdir()
    (digest / "digest.json").write_text("{}", encoding="utf-8")
    view = js.api_get_pools(home, client_ip="127.0.0.1", digest_home=digest)
    blob = json.dumps(view)
    assert "tokens_in" not in blob
    assert "tokens_out" not in blob
    assert "tokens_cached" not in blob
    assert "by_model" not in blob


def test_mrb6823_model_name_escaped():
    html = http._render_token_graph_html(
        {
            "state": "home",
            "unknown_jobs": 0,
            "by_model": [
                {
                    "model": "<script>x</script>",
                    "tokens_in": 3,
                    "tokens_out": 1,
                    "tokens_cached": 0,
                }
            ],
        }
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
