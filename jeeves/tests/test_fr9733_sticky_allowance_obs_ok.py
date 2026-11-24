"""FR #9733: sticky allowance exhausted must not hide fresher observation ok/unlimited."""
from __future__ import annotations

import json
import time
from pathlib import Path

import copilot_dispatch as cd


UNLIMITED = {
    "copilot_plan": "business",
    "quota_reset_date_utc": "2026-12-01T00:00:00.000Z",
    "quota_snapshots": {
        "premium_interactions": {
            "credits_used": 39,
            "entitlement": 0,
            "remaining": 0,
            "percent_remaining": 100.0,
            "unlimited": True,
            "overage_permitted": True,
        }
    },
}

NOW = 1_700_000_000.0


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _write_sticky_exhausted(home: Path, *, until_epoch: float, fetched_epoch: float) -> None:
    doc = {
        "state": "exhausted",
        "exhausted": True,
        "tasks_exhausted": True,
        "unlimited": False,
        "remaining": 0,
        "percent_remaining": 100,
        "fetched_at": _iso(fetched_epoch),
        "fetched_epoch": fetched_epoch,
        "exhausted_until": until_epoch,
        "exhausted_until_utc": _iso(until_epoch),
        "exhausted_until_source": "fallback-1st",
        "plan": "business",
    }
    home.mkdir(parents=True, exist_ok=True)
    (home / cd.ALLOWANCE_NAME).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def test_fr9733_pool_for_digest_fresher_obs_ok_beats_sticky_allowance(tmp_path: Path):
    """Systray/report path: newer observation ok/unlimited wins over sticky exhaust.

    Writes observation directly so this pin stays valid even when observe also clears sticky.
    """
    home = tmp_path / "digest"
    until = NOW + 30 * 24 * 3600
    _write_sticky_exhausted(home, until_epoch=until, fetched_epoch=NOW)
    obs = {
        "state": "ok",
        "unlimited": True,
        "remaining": 0,
        "percent_remaining": 100.0,
        "used": 39,
        "plan": "business",
        "fetched_at": _iso(NOW + 400),
        "fetched_epoch": NOW + 400,
        "attempted_at": _iso(NOW + 400),
        "source": "copilot_internal/user",
        "overage_permitted": True,
    }
    (home / cd.OBSERVATION_NAME).write_text(json.dumps(obs, indent=2) + "\n", encoding="utf-8")
    # Sticky allowance still exhausted on disk (observe clear not applied here).
    allow = cd.load_allowance(home)
    assert allow.get("tasks_exhausted") is True

    pool = cd.pool_for_digest(home)
    assert pool["state"] == "ok"
    assert pool["unlimited"] is True
    assert pool["percent_remaining"] == 100.0
    assert pool["fetched_at"] == _iso(NOW + 400)
    assert not (pool.get("resume_at") or "").strip()


def test_fr9733_observe_ok_clears_sticky_allowance_exhaust(tmp_path: Path):
    """observe_quota ok/unlimited clears sticky exhaust stamps (like refresh_allowance)."""
    home = tmp_path / "digest"
    until = NOW + 30 * 24 * 3600
    _write_sticky_exhausted(home, until_epoch=until, fetched_epoch=NOW)
    assert cd.cooldown_active(home, now=NOW + 10) is True

    cd.observe_quota(home, fetch_user=lambda: UNLIMITED, now=NOW + 400)
    allow = cd.load_allowance(home)
    assert allow.get("tasks_exhausted") is False
    assert allow.get("exhausted") is False
    assert "exhausted_until" not in allow or allow.get("exhausted_until") in (None, "")
    assert allow.get("state") == "ok"
    assert cd.cooldown_active(home, now=NOW + 410) is False


def test_fr9733_observe_ok_does_not_create_allowance_file(tmp_path: Path):
    """ok observation must not create copilot-allowance.json when absent."""
    home = tmp_path / "digest"
    home.mkdir(parents=True, exist_ok=True)
    cd.observe_quota(home, fetch_user=lambda: UNLIMITED, now=NOW)
    assert cd.observation_path(home).is_file()
    assert not cd._allow_path(home).is_file()
