"""FR #7522: 0% with known future reset is not stale (tray/ear/Jeeves rule)."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pool_reading_stale as prs  # noqa: E402

NOW = "2026-11-15T15:30:00Z"
OLD = "2026-11-15T10:00:00Z"  # >2 min old
FUTURE = "2026-12-01T00:00:00Z"
PAST = "2026-11-01T00:00:00Z"


def test_fr7522_zero_pct_future_reset_not_stale():
    assert (
        prs.is_pool_reading_stale(
            fetched_at=OLD,
            remaining_pct=0,
            period_end=FUTURE,
            now=NOW,
        )
        is False
    )
    assert (
        prs.should_report_pool_stale_exception(
            fetched_at=OLD,
            remaining_pct=0,
            reset_at=FUTURE,
            now=NOW,
        )
        is False
    )


def test_fr7522_zero_pct_past_reset_is_stale():
    assert (
        prs.is_pool_reading_stale(
            fetched_at=OLD,
            remaining_pct=0,
            period_end=PAST,
            now=NOW,
        )
        is True
    )


def test_fr7522_zero_pct_unknown_reset_is_stale():
    assert (
        prs.is_pool_reading_stale(
            fetched_at=OLD,
            remaining_pct=0,
            period_end=None,
            now=NOW,
        )
        is True
    )


def test_fr7522_fifty_pct_old_is_stale():
    assert (
        prs.is_pool_reading_stale(
            fetched_at=OLD,
            remaining_pct=50,
            period_end=FUTURE,
            now=NOW,
        )
        is True
    )


def test_fr7522_fifty_pct_fresh_not_stale():
    assert (
        prs.is_pool_reading_stale(
            fetched_at="2026-11-15T15:29:00Z",
            remaining_pct=50,
            period_end=FUTURE,
            now=NOW,
        )
        is False
    )


def test_fr7522_exhausted_held_helper():
    assert prs.exhausted_until_known_reset(
        remaining_pct=0, period_end=FUTURE, now=NOW
    )
    assert not prs.exhausted_until_known_reset(
        remaining_pct=1, period_end=FUTURE, now=NOW
    )


def test_fr7522_ear_reading_is_stale_honors_zero_pct_future_reset():
    import ear_pool_stale_report as epsr

    now = 1_700_000_000.0
    assert (
        epsr.reading_is_stale(
            fetched_at="2026-11-15T10:00:00Z",
            now=now,
            remaining_pct=0,
            period_end="2099-01-01T00:00:00Z",
        )
        is False
    )
    assert (
        epsr.reading_is_stale(
            fetched_at="2026-11-15T10:00:00Z",
            now=now,
            remaining_pct=50,
            period_end="2099-01-01T00:00:00Z",
        )
        is True
    )


def test_fr7522_fleet_held_exhausted_until_reset(tmp_path, monkeypatch):
    import bobreport
    import fleet_pool_fetch as fp

    home = tmp_path / "home"
    home.mkdir()
    bobreport.save_digest(home, bobreport.empty_digest())
    filed = []

    monkeypatch.setattr(
        fp,
        "file_fleet_pool_stale_exception",
        lambda **kw: filed.append(kw) or {"ok": True, "number": 1},
    )
    monkeypatch.setattr(fp, "comment_fleet_pool_stale_issue", lambda **k: True)

    now = 1_700_000_000.0
    # last_ok far in the past (>120s) but remaining 0 with future reset
    state = {
        fp.POOL_COPILOT: {
            "last_ok": now - 10_000,
            "last_attempt": now - 60,
            "error": None,
            "fail_streak": 0,
        }
    }
    fp._save_state(home, state)
    doc = bobreport.load_digest(home)
    doc["fleet_pools"] = {
        fp.POOL_COPILOT: {
            "id": fp.POOL_COPILOT,
            "remaining": 0,
            "reset_at": "2099-12-01T00:00:00Z",
            "fetched_at": "2026-11-01T00:00:00Z",
            "fresh": False,
        }
    }
    bobreport.save_digest(home, doc)
    out = fp.maybe_report_fleet_pool_staleness(home, now=now)
    assert out[fp.POOL_COPILOT]["action"] == "ok"
    assert filed == []
