"""FR #6435: DONE cost ledger idempotent per job; tokens are per-job deltas."""
from __future__ import annotations

import json
from pathlib import Path

import done_usage
import job_cost_ledger


def test_fr6435_repeated_done_writes_one_row(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    kwargs = dict(
        repo="o/r",
        ident="#6404",
        task="MRB",
        seat="redqueen-1",
        rest="PASS https://github.com/o/r/pull/6404 model=xai/a tokens_in=100 tokens_out=10 tokens_cached=1",
        url="https://github.com/o/r/pull/6404",
        done_at=1000.0,
    )
    r1 = job_cost_ledger.record_done(home, **kwargs)
    r2 = job_cost_ledger.record_done(home, **{**kwargs, "done_at": 1023.0})
    rows = job_cost_ledger.load_rows(home)
    assert len(rows) == 1
    assert r1["pr"] == "o/r#6404"
    assert r2["pr"] == "o/r#6404"
    assert rows[0].get("attempt") == 1
    assert rows[0].get("source")
    tot = job_cost_ledger.per_pr_totals(home, "o/r#6404")
    assert tot["jobs"] == 1
    assert tot["tokens_in"] == 100


def test_fr6435_distinct_attempt_keeps_two_rows(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    job_cost_ledger.record_done(
        home,
        repo="o/r",
        ident="#1",
        task="MRB",
        seat="s",
        rest="PASS https://github.com/o/r/pull/1 tokens_in=10 tokens_out=1 attempt=1 source=wire",
    )
    job_cost_ledger.record_done(
        home,
        repo="o/r",
        ident="#1",
        task="MRB",
        seat="s",
        rest="PASS https://github.com/o/r/pull/1 tokens_in=20 tokens_out=2 attempt=2 source=retry",
    )
    rows = job_cost_ledger.load_rows(home)
    assert len(rows) == 2
    attempts = sorted(int(r.get("attempt") or 0) for r in rows)
    assert attempts == [1, 2]


def test_fr6435_usage_delta_not_cumulative():
    baseline = {
        "model": "xai/grok-4.5",
        "tokens_in": 1000,
        "tokens_out": 200,
        "tokens_cached": 50,
        "tokens_unknown": False,
    }
    current = {
        "model": "xai/grok-4.5",
        "tokens_in": 1300,
        "tokens_out": 260,
        "tokens_cached": 80,
        "tokens_unknown": False,
    }
    d = done_usage.usage_delta(baseline, current)
    assert d["tokens_unknown"] is False
    assert d["tokens_in"] == 300
    assert d["tokens_out"] == 60
    assert d["tokens_cached"] == 30
    assert d["model"] == "xai/grok-4.5"


def test_fr6435_two_jobs_on_one_seat_record_own_deltas(tmp_path: Path):
    """Simulated cumulative seat totals: job1 100->150, job2 150->190 -> deltas 50 and 40."""
    home = tmp_path / "home"
    home.mkdir()
    # Job 6424
    u1 = done_usage.usage_delta(
        {"tokens_in": 100, "tokens_out": 10, "tokens_cached": 0, "tokens_unknown": False, "model": "xai/a"},
        {"tokens_in": 150, "tokens_out": 15, "tokens_cached": 2, "tokens_unknown": False, "model": "xai/a"},
    )
    job_cost_ledger.record_done(
        home,
        repo="SimonBarnett/bobiverse",
        ident="#6424",
        task="MRB",
        seat="redqueen-11768",
        rest=(
            f"PASS https://github.com/SimonBarnett/bobiverse/pull/6424 "
            f"model={u1['model']} tokens_in={u1['tokens_in']} "
            f"tokens_out={u1['tokens_out']} tokens_cached={u1['tokens_cached']}"
        ),
    )
    # Job 6425 — cumulative advanced, delta must differ
    u2 = done_usage.usage_delta(
        {"tokens_in": 150, "tokens_out": 15, "tokens_cached": 2, "tokens_unknown": False, "model": "xai/a"},
        {"tokens_in": 190, "tokens_out": 25, "tokens_cached": 5, "tokens_unknown": False, "model": "xai/a"},
    )
    job_cost_ledger.record_done(
        home,
        repo="SimonBarnett/bobiverse",
        ident="#6425",
        task="MRB",
        seat="redqueen-11768",
        rest=(
            f"PASS https://github.com/SimonBarnett/bobiverse/pull/6425 "
            f"model={u2['model']} tokens_in={u2['tokens_in']} "
            f"tokens_out={u2['tokens_out']} tokens_cached={u2['tokens_cached']}"
        ),
    )
    t1 = job_cost_ledger.per_pr_totals(home, "SimonBarnett/bobiverse#6424")
    t2 = job_cost_ledger.per_pr_totals(home, "SimonBarnett/bobiverse#6425")
    assert t1["tokens_in"] == 50
    assert t2["tokens_in"] == 40
    assert t1["tokens_in"] != t2["tokens_in"]


def test_fr6435_parse_attempt_and_source():
    u = done_usage.parse_done_usage(
        "PASS https://github.com/o/r/pull/1 tokens_in=1 tokens_out=1 attempt=3 source=replay"
    )
    assert u.get("attempt") == 3
    assert u.get("source") == "replay"


def test_fr6435_enrich_includes_attempt_source_when_set():
    suffix = done_usage.format_done_usage_suffix(
        {
            "model": "xai/a",
            "tokens_in": 1,
            "tokens_out": 2,
            "tokens_cached": 0,
            "tokens_unknown": False,
            "attempt": 2,
            "source": "retry",
        }
    )
    assert "attempt=2" in suffix
    assert "source=retry" in suffix
