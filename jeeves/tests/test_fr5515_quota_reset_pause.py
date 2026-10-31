"""FR #5515: Copilot out-of-tokens pause until quota_reset_date (else 1st of next month)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import copilot_dispatch as cd

NOW = 1_700_000_000.0  # 2023-11-14 22:13:20 UTC


def _epoch(y, m, d):
    return datetime(y, m, d, tzinfo=timezone.utc).timestamp()


def test_fr5515_api_date_pauses_until_that_midnight():
    until, source = cd.quota_pause_until(NOW, reset_date="2026-11-01", fuel="copilot")
    assert source == "api"
    assert until == _epoch(2026, 11, 1)


def test_fr5515_api_utc_field_uses_calendar_date():
    until, source = cd.quota_pause_until(
        NOW, reset_date="2026-11-01T15:30:00.000Z", fuel="copilot"
    )
    assert source == "api"
    assert until == _epoch(2026, 11, 1)


def test_fr5515_api_failure_falls_back_first_of_next_month():
    until, source = cd.quota_pause_until(NOW, reset_date="", fuel="copilot")
    assert source == "fallback-1st"
    assert until == _epoch(2023, 12, 1)


def test_fr5515_december_rolls_to_january():
    dec = datetime(2026, 12, 15, 8, 0, tzinfo=timezone.utc).timestamp()
    until, source = cd.quota_pause_until(dec, reset_date=None, fuel="copilot")
    assert source == "fallback-1st"
    assert until == _epoch(2027, 1, 1)


def test_fr5515_token_out_on_the_first_uses_following_month():
    first = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc).timestamp()
    until, source = cd.quota_pause_until(first, reset_date=None, fuel="copilot")
    assert source == "fallback-1st"
    assert until == _epoch(2026, 12, 1)


def test_fr5515_token_out_on_the_first_honours_future_api_date():
    first = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc).timestamp()
    until, source = cd.quota_pause_until(first, reset_date="2026-12-01", fuel="copilot")
    assert source == "api"
    assert until == _epoch(2026, 12, 1)


def test_fr5515_stale_api_date_on_the_first_falls_back():
    """quota_reset_date of today at 00:00 UTC is already past at noon; must not unpause."""
    first = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc).timestamp()
    until, source = cd.quota_pause_until(first, reset_date="2026-11-01", fuel="copilot")
    assert source == "fallback-1st"
    assert until == _epoch(2026, 12, 1)
    assert until > first


def test_fr5515_bad_api_date_falls_back():
    until, source = cd.quota_pause_until(NOW, reset_date="not-a-date", fuel="copilot")
    assert source == "fallback-1st"
    assert until == _epoch(2023, 12, 1)


def test_fr5515_cursor_keeps_seven_days_without_reset():
    until, source = cd.quota_pause_until(NOW, reset_date=None, fuel="cursor")
    assert source == "fixed-7d"
    assert until == NOW + 7 * 86400


def test_fr5515_cursor_uses_reset_when_given():
    until, source = cd.quota_pause_until(NOW, reset_date="2026-11-01", fuel="cursor")
    assert source == "api"
    assert until == _epoch(2026, 11, 1)


def test_fr5515_mark_persists_source_and_survives_reload(tmp_path):
    announced: list[str] = []
    out = cd.mark_tokens_exhausted(
        tmp_path,
        now=NOW,
        reset_date="2026-11-01",
        announce=announced.append,
    )
    assert out["exhausted_until"] == _epoch(2026, 11, 1)
    assert out.get("source") == "api"
    raw = json.loads((tmp_path / cd.ALLOWANCE_NAME).read_text(encoding="utf-8"))
    assert raw["exhausted_until"] == _epoch(2026, 11, 1)
    assert raw["exhausted_until_source"] == "api"
    assert cd.cooldown_active(tmp_path, now=NOW)
    assert cd.cooldown_active(tmp_path, now=_epoch(2026, 10, 31))
    assert not cd.cooldown_active(tmp_path, now=_epoch(2026, 11, 1) + 1)
    pool = cd.pool_for_digest(tmp_path)
    assert pool["resume_at"]
    assert pool.get("resume_source") == "api"
    assert announced and "paused until" in announced[0].lower()


def test_fr5515_refresh_exhausted_uses_api_reset(tmp_path):
    def fetch():
        return {
            "quota_reset_date": "2026-11-01",
            "quota_snapshots": {
                "premium_interactions": {"remaining": 0, "percent_remaining": 0}
            },
        }

    cd.refresh_allowance(tmp_path, fetch_user=fetch, now=NOW)
    raw = json.loads((tmp_path / cd.ALLOWANCE_NAME).read_text(encoding="utf-8"))
    assert raw["exhausted_until"] == _epoch(2026, 11, 1)
    assert raw["exhausted_until_source"] == "api"


def test_fr5515_refresh_fetch_error_falls_back_first(tmp_path):
    def fetch():
        raise RuntimeError("api down")

    # unknown parse is not exhausted; simulate token-out via mark after failed fetch
    cd.refresh_allowance(tmp_path, fetch_user=fetch, now=NOW)
    cd.mark_tokens_exhausted(tmp_path, now=NOW, announce=lambda *_a: None)
    raw = json.loads((tmp_path / cd.ALLOWANCE_NAME).read_text(encoding="utf-8"))
    assert raw["exhausted_until"] == _epoch(2023, 12, 1)
    assert raw["exhausted_until_source"] == "fallback-1st"


def test_fr5515_pins():
    from pathlib import Path

    src = Path(cd.__file__).read_text(encoding="utf-8")
    assert "FR #5515" in src
    assert "quota_pause_until" in src
    assert "fallback-1st" in src
    assert not Path(cd.__file__).read_bytes().startswith(b"\xef\xbb\xbf")
