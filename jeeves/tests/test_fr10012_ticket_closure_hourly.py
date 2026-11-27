"""FR #10012: ticket-closure backup is hourly and skips while GitHub is in backoff."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import chair_health as ch  # noqa: E402


def test_fr10012_default_hourly_and_backoff_skips(tmp_path, monkeypatch):
    monkeypatch.delenv("JEEVES_TICKET_CLOSURE_S", raising=False)
    assert ch.TICKET_CLOSURE_S == 3600.0
    assert ch.ticket_closure_interval_s() == 3600.0
    (tmp_path / "github-api-budget.json").write_text(
        json.dumps({"v": 1, "hour": 0, "used": 0, "rate_remaining": 0, "rate_reset": 9e12}),
        encoding="utf-8",
    )
    out = ch.run_ticket_closure_cycle(chair_home=tmp_path, digest_home=tmp_path)
    assert out.get("skipped") == "github-backoff"
