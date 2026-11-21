"""FR #8649: an explicit Cursor start uses the si@ntsa.uk pool, not local fuel."""
from __future__ import annotations

from datetime import datetime, timezone

import bob.scripts.bob_worker as bw
import bobreport


CUR = r"C:\cursor\agent.cmd"
ACCOUNT = "si@ntsa.uk"


def _iso(now: float) -> str:
    return (
        datetime.fromtimestamp(now, timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _local_empty():
    return bw.Fuel(
        cursor_high=None,
        cursor_low=None,
        grok_pct=0,
        grok_state="exhausted",
        overspend_state="at-limit",
        on_demand_used_cents=100,
        on_demand_limit_cents=100,
    )


def test_explicit_cursor_starts_when_local_pool_unknown():
    dec = bw.explicit_agent_decision(
        "cursor", _local_empty(), CUR, r"C:\g\agent.exe", None, auth_present=True
    )
    assert dec.kind == "cursor"
    assert dec.account == ACCOUNT
    assert "account=%s" % ACCOUNT in dec.reason
    assert "remaining=unknown" in dec.reason
    assert "no tokens" not in dec.reason
    assert "high=" not in dec.reason


def test_explicit_cursor_refuses_only_si_pool_zero():
    now = 1_700_000_000.0
    digest = {
        "fleet_pools": {
            "cursor": {
                "remaining": 0,
                "fresh": True,
                "fetched_at": _iso(now),
                "source": "credman:hidden",
            }
        }
    }
    dec = bw.explicit_cursor_si_decision(CUR, digest, now=now)
    assert dec.kind == "refuse"
    assert ACCOUNT in dec.reason
    assert "remaining=0" in dec.reason
    assert "credman" not in dec.reason
    assert "hidden" not in dec.reason
    assert dec.kind != "grok"
    assert dec.kind != "opencode"


def test_explicit_cursor_uses_fresh_si_remaining():
    now = 1_700_000_000.0
    digest = {
        "fleet_pools": {
            "cursor": {"remaining": 40, "fresh": True, "fetched_at": _iso(now)}
        }
    }
    dec = bw.resolve_seat_decision(
        "cursor",
        bw.Decision("dialog", "auto"),
        _local_empty(),
        CUR,
        r"C:\g\agent.exe",
        None,
        auth_present=True,
        fleet_digest=digest,
        now=now,
    )
    assert dec.kind == "cursor"
    assert "remaining=40" in dec.reason
    assert dec.account == ACCOUNT


def test_explicit_cursor_missing_cmd_does_not_substitute():
    dec = bw.explicit_agent_decision(
        "cursor", _local_empty(), None, r"C:\g\agent.exe", r"C:\o\opencode.exe", auth_present=True
    )
    assert dec.kind == "refuse"
    assert "agent.cmd missing" in dec.reason


def test_automatic_selection_still_requires_local_cursor_tokens():
    fuel = _local_empty()
    dec = bw.select_agent(fuel, CUR, None, None)
    assert dec.kind != "cursor"
    assert bw.cursor_has_tokens(fuel) is False


def test_digest_keeps_si_account_label_only():
    worker = bobreport._coerce_worker(
        "marchhare",
        "10",
        {
            "nick": "marchhare-10",
            "kind": "cursor",
            "cursor_account": ACCOUNT,
            "source": "credman:hidden",
        },
    )
    assert worker["cursor_account"] == ACCOUNT
    assert "source" not in worker
    blocked = bobreport._coerce_worker(
        "marchhare",
        "11",
        {"nick": "marchhare-11", "kind": "cursor", "cursor_account": "not-the-fleet-account"},
    )
    assert "cursor_account" not in blocked
