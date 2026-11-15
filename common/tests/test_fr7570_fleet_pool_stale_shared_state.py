"""FR #7570: fleet-pool-stale reporter uses fetcher shared state only."""
from __future__ import annotations

from pathlib import Path

import bobreport
import fleet_pool_fetch as fp

NOW = 1_700_000_000.0


def _home(tmp: Path) -> Path:
    home = tmp / "home"
    home.mkdir()
    bobreport.save_digest(home, bobreport.empty_digest())
    return home


def test_fr7570_fresh_fetcher_state_empty_digest_does_not_file(tmp_path: Path, monkeypatch):
    """Fetcher state fresh/ok while digest/credential view empty: no report."""
    home = _home(tmp_path)
    filed: list[dict] = []
    monkeypatch.setattr(
        fp,
        "file_fleet_pool_stale_exception",
        lambda **kw: filed.append(dict(kw)) or {"ok": True, "number": 1},
    )
    # Shared fetcher state: live ok just now.
    fp._save_state(
        home,
        {
            fp.POOL_COPILOT: {
                "last_ok": NOW,
                "last_attempt": NOW,
                "first_attempt": NOW - 600,
                "error": None,
                "fail_streak": 0,
            },
            fp.POOL_OC_GO: {
                "last_ok": NOW,
                "last_attempt": NOW,
                "first_attempt": NOW - 600,
                "error": None,
                "fail_streak": 0,
            },
        },
    )
    # Empty digest fleet_pools (reporter must not invent no_token from missing digest row).
    doc = bobreport.load_digest(home)
    doc["fleet_pools"] = {}
    bobreport.save_digest(home, doc)

    out = fp.maybe_report_fleet_pool_staleness(home, now=NOW + 5)
    assert out[fp.POOL_COPILOT]["action"] == "ok"
    assert out[fp.POOL_OC_GO]["action"] == "ok"
    assert filed == []


def test_fr7570_stale_last_ok_files_with_real_last_ok(tmp_path: Path, monkeypatch):
    home = _home(tmp_path)
    filed: list[dict] = []
    monkeypatch.setattr(
        fp,
        "file_fleet_pool_stale_exception",
        lambda **kw: filed.append(dict(kw)) or {"ok": True, "number": 9100, "deduped": False},
    )
    monkeypatch.setattr(fp, "comment_fleet_pool_stale_issue", lambda **k: True)
    last_ok = NOW
    now = NOW + 180  # 3 min stale
    fp._save_state(
        home,
        {
            fp.POOL_COPILOT: {
                "last_ok": last_ok,
                "last_attempt": last_ok + 10,
                "first_attempt": last_ok - 1000,
                "error": "provider-http-500",
                "fail_streak": 2,
            }
        },
    )
    doc = bobreport.load_digest(home)
    doc["fleet_pools"] = {
        fp.POOL_COPILOT: {
            "id": fp.POOL_COPILOT,
            "fetched_at": "2026-11-15T12:00:00Z",
            "remaining": 40,
            "error": "provider-http-500",
            "fresh": False,
        }
    }
    bobreport.save_digest(home, doc)
    out = fp.maybe_report_fleet_pool_staleness(home, now=now)
    assert out[fp.POOL_COPILOT]["action"] == "filed"
    assert len(filed) == 1
    body = filed[0]["body"]
    assert "last_ok" in body.lower()
    assert "2026-11-15" in body or "1700000000" in body
    assert "provider-http-500" in body
    assert "(none)" not in body or "last_ok" in body.lower()


def test_fr7570_startup_grace_before_first_fetch(tmp_path: Path, monkeypatch):
    home = _home(tmp_path)
    filed: list[dict] = []
    monkeypatch.setattr(
        fp,
        "file_fleet_pool_stale_exception",
        lambda **kw: filed.append(dict(kw)) or {"ok": True, "number": 2},
    )
    # First minute: first_attempt set, never ok, empty digest.
    fp._save_state(
        home,
        {
            fp.POOL_COPILOT: {
                "first_attempt": NOW,
                "last_attempt": NOW,
                "last_ok": 0.0,
                "error": "no_token",
            }
        },
    )
    out = fp.maybe_report_fleet_pool_staleness(home, now=NOW + 30)
    assert out[fp.POOL_COPILOT]["action"] == "startup-grace"
    assert filed == []


def test_fr7570_shared_snapshot_helper_prefers_state_last_ok():
    st = {"last_ok": NOW, "error": None, "first_attempt": NOW - 10}
    row = {}  # empty digest / credential view
    snap = fp.fleet_pool_shared_snapshot(st, row, now=NOW + 5)
    assert snap["last_ok"] == NOW
    assert snap["age_s"] is not None and snap["age_s"] < 60
    assert snap["fetched_at"]  # derived from last_ok when digest empty
    assert snap["error"] in (None, "")
