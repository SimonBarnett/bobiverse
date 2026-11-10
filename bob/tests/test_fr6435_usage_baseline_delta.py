"""FR #6435: worker DONE stamp uses per-job delta from ACK baseline."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bob" / "scripts"))
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import bob_worker as bw
import done_usage


class _Sup:
    kind = "grok"
    cwd = ""
    sessions = []
    sessions_root = None
    run_dir = None

    def __init__(self, run_dir: Path, usage_path: Path):
        self.run_dir = run_dir
        self._usage_path = usage_path
        self.cwd = str(run_dir)
        self.sessions_root = run_dir

    def measure_done_usage(self, *, apply_baseline: bool = True):
        # Delegate to real Supervisor helpers via a thin stand-in.
        return bw.Supervisor.measure_done_usage(self, apply_baseline=apply_baseline)

    def _usage_baseline_path(self):
        return Path(self.run_dir) / "usage-baseline.json"

    def snapshot_usage_baseline(self, job: str = ""):
        usage = self.measure_done_usage(apply_baseline=False)
        done_usage.save_usage_baseline(self._usage_baseline_path(), usage, job=job)

    def _measure_opencode_usage(self, oc_path):
        return {"tokens_unknown": True}


def test_fr6435_worker_done_uses_ack_baseline_delta(tmp_path: Path, monkeypatch):
    run = tmp_path / "run"
    run.mkdir()
    usage_path = run / "usage.json"
    # cumulative at ACK
    usage_path.write_text(
        json.dumps({"session": {"inputTokens": 100, "outputTokens": 20, "cachedReadTokens": 5, "primaryModelId": "grok-4.5"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOB_GROK_USAGE_PATH", str(usage_path))
    sup = _Sup(run, usage_path)
    # Bind methods that Supervisor defines for path/baseline
    sup._usage_baseline_path = lambda: run / "usage-baseline.json"  # type: ignore
    bw.Supervisor.snapshot_usage_baseline(sup, job="MRB o/r#1")
    # cumulative at DONE
    usage_path.write_text(
        json.dumps({"session": {"inputTokens": 160, "outputTokens": 35, "cachedReadTokens": 9, "primaryModelId": "grok-4.5"}}),
        encoding="utf-8",
    )
    usage = bw.Supervisor.measure_done_usage(sup, apply_baseline=True)
    assert usage["tokens_in"] == 60
    assert usage["tokens_out"] == 15
    assert usage["tokens_cached"] == 4
    line = done_usage.enrich_done_payload(
        "DONE MRB o/r#1 PASS https://github.com/o/r/pull/1", usage
    )
    assert "tokens_in=60" in line
    assert "tokens_out=15" in line
