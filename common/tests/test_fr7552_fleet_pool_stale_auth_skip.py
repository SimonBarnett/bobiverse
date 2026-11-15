"""FR #7552 / #7553: no_token / no_key must not file fleet-pool-stale exceptions."""
from __future__ import annotations

from pathlib import Path

import bobreport
import fleet_pool_fetch as fp

NOW = 1_700_000_000.0
STALE = NOW + 130.0


def _home(tmp: Path) -> Path:
    home = tmp / "home"
    home.mkdir()
    bobreport.save_digest(home, bobreport.empty_digest())
    return home


def test_fr7552_auth_skip_classifier():
    assert fp.is_fleet_pool_auth_skip_error("no_token")
    assert fp.is_fleet_pool_auth_skip_error("no_key")
    assert fp.is_fleet_pool_auth_skip_error("missing_key")
    assert fp.is_fleet_pool_auth_skip_error("not installed")
    assert not fp.is_fleet_pool_auth_skip_error("provider-http-500")
    assert not fp.is_fleet_pool_auth_skip_error("")


def test_fr7552_copilot_no_token_never_ok_does_not_file(tmp_path: Path, monkeypatch):
    home = _home(tmp_path)
    filed: list[dict] = []

    monkeypatch.setattr(
        fp,
        "file_fleet_pool_stale_exception",
        lambda **kw: filed.append(dict(kw)) or {"ok": True, "number": 1},
    )
    monkeypatch.setattr(fp, "comment_fleet_pool_stale_issue", lambda **k: True)

    # Never succeeded; first attempt >120s ago; auth error matches intake #7552.
    state = {
        fp.POOL_COPILOT: {
            "first_attempt": NOW,
            "last_attempt": NOW + 60,
            "last_ok": 0.0,
            "error": "no_token",
            "fail_streak": 3,
        }
    }
    fp._save_state(home, state)
    doc = bobreport.load_digest(home)
    doc["fleet_pools"] = {
        fp.POOL_COPILOT: {
            "id": fp.POOL_COPILOT,
            "fetched_at": None,
            "error": "no_token",
            "fresh": False,
        }
    }
    bobreport.save_digest(home, doc)

    out = fp.maybe_report_fleet_pool_staleness(home, now=STALE)
    assert out[fp.POOL_COPILOT]["action"] == "skipped-auth"
    assert filed == []


def test_fr7553_opencode_no_key_never_ok_does_not_file(tmp_path: Path, monkeypatch):
    home = _home(tmp_path)
    filed: list[dict] = []
    monkeypatch.setattr(
        fp,
        "file_fleet_pool_stale_exception",
        lambda **kw: filed.append(dict(kw)) or {"ok": True, "number": 2},
    )
    monkeypatch.setattr(fp, "comment_fleet_pool_stale_issue", lambda **k: True)

    state = {
        fp.POOL_OC_GO: {
            "first_attempt": NOW,
            "last_attempt": NOW + 60,
            "last_ok": 0.0,
            "error": "no_key",
            "fail_streak": 2,
        }
    }
    fp._save_state(home, state)
    out = fp.maybe_report_fleet_pool_staleness(home, now=STALE)
    assert out[fp.POOL_OC_GO]["action"] == "skipped-auth"
    assert filed == []


def test_fr7552_provider_error_still_files(tmp_path: Path, monkeypatch):
    home = _home(tmp_path)
    filed: list[dict] = []
    monkeypatch.setattr(
        fp,
        "file_fleet_pool_stale_exception",
        lambda **kw: filed.append(dict(kw)) or {"ok": True, "number": 9002, "deduped": False},
    )
    monkeypatch.setattr(fp, "comment_fleet_pool_stale_issue", lambda **k: True)
    state = {
        fp.POOL_COPILOT: {
            "last_ok": NOW,
            "last_attempt": NOW + 60,
            "error": "provider-http-500",
            "fail_streak": 2,
        }
    }
    fp._save_state(home, state)
    doc = bobreport.load_digest(home)
    doc["fleet_pools"] = {
        fp.POOL_COPILOT: {
            "id": fp.POOL_COPILOT,
            "fetched_at": "2026-11-15T14:00:00Z",
            "error": "provider-http-500",
            "fresh": False,
        }
    }
    bobreport.save_digest(home, doc)
    out = fp.maybe_report_fleet_pool_staleness(home, now=STALE)
    assert out[fp.POOL_COPILOT]["action"] == "filed"
    assert len(filed) == 1


def test_fr7552_open_auth_issue_gets_held_comment(tmp_path: Path, monkeypatch):
    home = _home(tmp_path)
    comments: list[dict] = []
    monkeypatch.setattr(
        fp,
        "comment_fleet_pool_stale_issue",
        lambda **kw: comments.append(dict(kw)) or True,
    )
    monkeypatch.setattr(
        fp,
        "file_fleet_pool_stale_exception",
        lambda **k: (_ for _ in ()).throw(AssertionError("must not file")),
    )
    state = {
        fp.POOL_COPILOT: {
            "first_attempt": NOW,
            "last_attempt": STALE,
            "last_ok": 0.0,
            "error": "no_token",
            "stale_issue": 7552,
            "stale_open": True,
        }
    }
    fp._save_state(home, state)
    out = fp.maybe_report_fleet_pool_staleness(home, now=STALE)
    assert out[fp.POOL_COPILOT]["action"] == "held-auth"
    assert len(comments) == 1
    assert "no_token" in comments[0]["body"]
    assert comments[0]["number"] == 7552
    st = fp._load_state(home)[fp.POOL_COPILOT]
    assert st.get("stale_open") is False
