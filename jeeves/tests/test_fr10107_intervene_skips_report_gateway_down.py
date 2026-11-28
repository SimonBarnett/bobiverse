"""FR #10107: no blind intervene_assign when public /report is 502."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))
sys.path.insert(0, str(ROOT / "jeeves" / "tools" / "monitor"))

import intervene_assign as ia  # noqa: E402


class _Args:
    dry_run = False
    fixture = ""
    chair_home = ""
    digest_home = ""
    ear_outbox = ""
    intervene_dry_run = True
    force_needs_human = False
    pace_s = 3.0
    max_assigns = 8
    truncate_outbox = False
    prefer_shop_wire_on_mute = False
    shop_wire = False
    cmd_trace_mute_s = 0.0
    chair_outbox = ""
    allow_fast_pace = True


def test_intervene_assign_skips_when_report_gateway_down(monkeypatch):
    monkeypatch.setattr(
        ia,
        "live_report_gateway_down",
        lambda **_k: {"gateway_down": True, "status": 502, "doc": None, "error": "HTTPError:502"},
    )
    payload, code = ia.check(_Args())
    assert code == ia.EXIT_OK
    assert payload.get("skipped") == "report_gateway_down"
    assert payload.get("report_http_status") == 502
    assert any("10107" in f for f in payload.get("findings") or [])


def test_plan_assigns_can_drop_opencode_seats(monkeypatch):
    monkeypatch.setenv("BOB_MONITOR_SKIP_OPENCODE_SEATS", "1")
    idle = [
        {"nick": "redqueen-1", "state": "idle", "kind": "opencode"},
        {"nick": "marchhare-2", "state": "idle", "kind": "grok"},
    ]
    rows = [
        {
            "repo": "SimonBarnett/bobiverse",
            "id": "10107",
            "task": "FR",
        }
    ]
    planned = ia.plan_assigns(idle, rows, max_assigns=2)
    assert planned
    assert all("opencode" not in p["nick"] for p in planned)
    planned_oc = ia.plan_assigns(
        [{"nick": "redqueen-1", "state": "idle", "kind": "opencode"}],
        rows,
        max_assigns=1,
    )
    assert planned_oc == []