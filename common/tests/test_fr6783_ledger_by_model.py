"""FR #6783: job_costs.by_model rollup groups measured rows; unknown stays out of sums."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import job_cost_ledger  # noqa: E402


def test_by_model_rollup_two_models_and_unknown(tmp_path: Path):
    """S3: two Grok + one Cursor measured, one unknown -> two buckets, unknown_jobs=1."""
    home = tmp_path / "home"
    home.mkdir()
    job_cost_ledger.record_done(
        home,
        repo="o/r",
        ident="#1",
        task="FR",
        seat="a",
        rest="https://github.com/o/r/pull/1 model=xai/grok-4.5 tokens_in=100 tokens_out=20 tokens_cached=5",
    )
    job_cost_ledger.record_done(
        home,
        repo="o/r",
        ident="#2",
        task="FR",
        seat="b",
        rest="https://github.com/o/r/pull/2 model=xai/grok-4.5 tokens_in=50 tokens_out=10 tokens_cached=2",
    )
    job_cost_ledger.record_done(
        home,
        repo="o/r",
        ident="#3",
        task="FR",
        seat="c",
        rest="https://github.com/o/r/pull/3 model=cursor/composer-1 tokens_in=40 tokens_out=8 tokens_cached=1",
    )
    job_cost_ledger.record_done(
        home,
        repo="o/r",
        ident="#4",
        task="FR",
        seat="d",
        rest="https://github.com/o/r/pull/4 tokens=unknown",
    )

    summary = job_cost_ledger.summarize(job_cost_ledger.load_rows(home))
    by_model = summary.get("by_model")
    assert isinstance(by_model, list)
    assert len(by_model) == 2
    assert summary.get("unknown_jobs") == 1

    by_id = {b["model"]: b for b in by_model}
    assert set(by_id) == {"xai/grok-4.5", "cursor/composer-1"}

    grok = by_id["xai/grok-4.5"]
    assert grok["measured_jobs"] == 2
    assert grok["tokens_in"] == 150
    assert grok["tokens_out"] == 30
    assert grok["tokens_cached"] == 7

    cursor = by_id["cursor/composer-1"]
    assert cursor["measured_jobs"] == 1
    assert cursor["tokens_in"] == 40
    assert cursor["tokens_out"] == 8
    assert cursor["tokens_cached"] == 1

    digest = job_cost_ledger.digest_section(home)
    assert digest.get("unknown_jobs") == 1
    assert isinstance(digest.get("by_model"), list)
    assert len(digest["by_model"]) == 2
    d_by = {b["model"]: b for b in digest["by_model"]}
    assert d_by["xai/grok-4.5"]["tokens_in"] == 150
    assert d_by["cursor/composer-1"]["tokens_cached"] == 1
