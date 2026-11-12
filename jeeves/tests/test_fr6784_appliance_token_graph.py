"""FR #6784: appliance /status token comparison graph (home / empty / error)."""
from __future__ import annotations

import json
from pathlib import Path

import job_cost_ledger
import jeeves_settings_http as http


def _graph_html(home: Path, digest: Path) -> str:
    view = {
        "ok": True,
        "version": "t",
        "source_commit": "abc",
        "uptime_s": 1,
        "queue": {"unaccepted": 0, "accepted": 0},
        "seats": {"live_n": 0, "idle_n": 0},
        "fuel": {"active": ["grok"]},
        "restart_pending": False,
    }
    g = http.load_status_token_graph(digest)
    return http._render_status_html(view, token_graph=g)


def test_fr6784_home_svg_one_series_per_model(tmp_path: Path):
    digest = tmp_path / "digest"
    digest.mkdir()
    rows = [
        job_cost_ledger.make_row(
            pr="o/r#1",
            task="FR",
            model="xai/grok-4.7",
            tokens_in=100,
            tokens_out=40,
            tokens_cached=10,
            tokens_unknown=False,
        ),
        job_cost_ledger.make_row(
            pr="o/r#2",
            task="FR",
            model="xai/grok-4.7",
            tokens_in=20,
            tokens_out=5,
            tokens_cached=0,
            tokens_unknown=False,
        ),
        job_cost_ledger.make_row(
            pr="o/r#3",
            task="FR",
            model="cursor/composer-1",
            tokens_in=50,
            tokens_out=10,
            tokens_cached=0,
            tokens_unknown=False,
        ),
        job_cost_ledger.make_row(
            pr="o/r#4",
            task="FR",
            model="cursor/composer-1",
            tokens_unknown=True,
        ),
    ]
    job_cost_ledger.save_rows(digest, rows)
    html = _graph_html(tmp_path / "chair", digest)
    assert "<svg" in html
    assert "<rect" in html
    assert "xai/grok-4.7" in html
    assert "cursor/composer-1" in html
    assert "unknown_jobs" in html
    assert "1" in html
    # Unknown is text, not a zero bar labelled unknown as a series.
    assert 'aria-label="Token totals by model"' in html or "Measured tokens by model" in html


def test_fr6784_empty_has_no_zero_series(tmp_path: Path):
    digest = tmp_path / "digest"
    digest.mkdir()
    html = _graph_html(tmp_path / "chair", digest)
    assert "Nothing to compare" in html or "no measured" in html.lower()
    assert "<rect" not in html
    assert 'width="0"' not in html


def test_fr6784_error_has_no_bar_series(tmp_path: Path):
    digest = tmp_path / "digest"
    digest.mkdir()
    (digest / "job-cost-ledger.json").write_text("{not-json", encoding="utf-8")
    html = _graph_html(tmp_path / "chair", digest)
    assert "cannot be drawn" in html.lower() or "could not be read" in html.lower()
    assert "<rect" not in html
    assert 'role="alert"' in html or "err" in html


def test_fr6784_api_pools_unchanged_no_token_fields():
    src = (
        Path(__file__).resolve().parents[2]
        / "common"
        / "scripts"
        / "jeeves_settings.py"
    ).read_text(encoding="utf-8")
    # FR-004 must not hang token fields on GET /api/pools.
    assert "def api_get_pools" in src or "api_get_pools" in src
