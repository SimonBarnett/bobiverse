"""FR #8667: private si Cursor meter drives remaining=0 refuse."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import bob.scripts.bob_worker as bw
import fleet_pool_fetch as fpf


ACCOUNT = "si@ntsa.uk"
CUR = r"C:\cursor\agent.cmd"


def _iso(now: float) -> str:
    return (
        datetime.fromtimestamp(now, timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def test_private_zero_refuses_without_public_digest(tmp_path: Path):
    now = 1_700_000_000.0
    row = {
        "remaining": 0,
        "fresh": True,
        "fetched_at": _iso(now),
        "source": "credman:hidden",
    }
    fpf.write_private_cursor_meter(tmp_path, row)
    loaded = fpf.load_private_cursor_meter(tmp_path)
    assert loaded is not None
    assert loaded["remaining"] == 0
    assert "credman" not in str(loaded.get("source") or "")
    # Public digest omits cursor (FR #7326).
    digest = {"fleet_pools": {"copilot": {"remaining": 1, "fresh": True}}}
    import bobreport

    cleaned = bobreport._digest_fleet_pools({"fleet_pools": {"cursor": row, "copilot": {"remaining": 1}}})
    assert "cursor" not in cleaned
    dec = bw.explicit_cursor_si_decision(
        CUR, digest, now=now, private_cursor=loaded, install_root=tmp_path
    )
    assert dec.kind == "refuse"
    assert ACCOUNT in dec.reason
    assert "remaining=0" in dec.reason


def test_private_unknown_still_starts(tmp_path: Path):
    dec = bw.explicit_cursor_si_decision(
        CUR, {}, now=1_700_000_000.0, private_cursor=None, install_root=tmp_path
    )
    assert dec.kind == "cursor"
    assert "remaining=unknown" in dec.reason


def test_tick_writes_private_cursor(tmp_path: Path, monkeypatch):
    now = 1_700_000_000.0

    def fake_cursor(home, n):
        return {
            "id": "cursor",
            "remaining": 0,
            "fetched_at": _iso(n),
            "last_attempt_at": _iso(n),
            "error": None,
            "source": "credman:hidden",
            "fresh": True,
        }

    monkeypatch.setattr(fpf, "fetch_copilot_default", lambda h, n: fpf.empty_meter(pool_id="copilot", source="t", now=n))
    monkeypatch.setattr(fpf, "fetch_opencode_default", lambda h, n: {})
    # force due
    monkeypatch.setattr(fpf, "pool_due", lambda *a, **k: True)
    monkeypatch.setattr(fpf, "apply_fleet_pools_to_digest", lambda *a, **k: None)
    monkeypatch.setattr(fpf, "maybe_report_fleet_pool_staleness", lambda *a, **k: None)
    fpf.tick_fleet_pools(tmp_path, now=now, fetch_cursor=fake_cursor)
    loaded = fpf.load_private_cursor_meter(tmp_path)
    assert loaded is not None
    assert loaded["remaining"] == 0
    assert loaded["fresh"] is True
    # Digests must not regain public cursor from this tick.
    # apply stubbed; private file is the contract.
    dec = bw.explicit_cursor_si_decision(CUR, {}, now=now, install_root=tmp_path)
    assert dec.kind == "refuse"
    assert "remaining=0" in dec.reason
