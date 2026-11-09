"""FR #6270: LocalSystem xAI weekly reads interactive user unified.jsonl.

Fixtures use remaining 61 (used 39) — never the live 82/74/43 set.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import bobreport  # noqa: E402


def _billing(used_pct: float = 39.0, remaining_hint: int = 61) -> str:
    del remaining_hint
    return (
        '{"ts":"2026-11-09T06:00:00Z","msg":"billing: fetched credits config",'
        '"ctx":{"config":{"currentPeriod":{"type":"USAGE_PERIOD_TYPE_WEEKLY",'
        '"end":"2026-11-16T12:00:00Z"},"creditUsagePercent":%s}}}\n' % used_pct
    )


def test_fr6270_interactive_home_env_beats_system_profile(monkeypatch, tmp_path: Path):
    user = tmp_path / "Users" / "FleetAdmin"
    log = user / ".grok" / "logs" / "unified.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text(_billing(39.0), encoding="utf-8")
    monkeypatch.delenv("BOB_WEEKLY_LOG", raising=False)
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "systemprofile"))
    (tmp_path / "systemprofile").mkdir(exist_ok=True)
    monkeypatch.setenv("BOB_GROK_WEEKLY_USER_HOME", str(user))
    monkeypatch.setenv("USERNAME", "tester")  # not live LocalSystem
    path, identity = bobreport.xai_weekly_log_candidate()
    assert identity == "interactive-profile"
    assert path == log
    now = datetime(2026, 11, 9, 7, 0, tzinfo=timezone.utc)
    reading = bobreport.read_local_xai_weekly(now=now)
    assert reading is not None
    assert reading["remaining_pct"] == 61
    assert reading["weekly_known"] is True
    assert reading.get("fetched_at")
    assert bobreport._last_xai_acquisition["identity"] == "interactive-profile"


def test_fr6270_system_profile_still_skipped_without_interactive_log(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("BOB_WEEKLY_LOG", raising=False)
    monkeypatch.delenv("BOB_GROK_WEEKLY_USER_HOME", raising=False)
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "systemprofile"))
    (tmp_path / "systemprofile").mkdir(exist_ok=True)
    monkeypatch.setenv("USERNAME", "tester")
    path, identity = bobreport.xai_weekly_log_candidate()
    assert path is None
    assert identity == "system-profile-skipped"
    assert bobreport.read_local_xai_weekly() is None
    assert bobreport._last_xai_acquisition["identity"] == "system-profile-skipped"

def test_fr6270_publish_skips_do_not_carry_stale_weekly(monkeypatch, tmp_path: Path):
    """Ear publish must clear carried weekly when acquisition is system-profile-skipped.

    Fixtures: prior peer weekly=19; skip leaves weekly unknown (never re-post 19).
    """
    import json
    from unittest import mock

    import bobstat

    home = tmp_path / "home"
    home.mkdir()
    mid = "marchhare"
    bobstat.write_peer(
        home,
        {
            "ok": True,
            "id": mid,
            "online": True,
            "status": "operational",
            "weekly": 19,
            "weekly_known": True,
            "pcent": {"grok-build": 19},
            "lastSeen": "2026-11-09T06:00:00Z",
        },
    )
    monkeypatch.delenv("BOB_WEEKLY_LOG", raising=False)
    monkeypatch.delenv("BOB_GROK_WEEKLY_USER_HOME", raising=False)
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "systemprofile"))
    (tmp_path / "systemprofile").mkdir(exist_ok=True)
    monkeypatch.setenv("USERNAME", "tester")

    posted: list[dict] = []

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        posted.append(json.loads(req.data.decode("utf-8")))

        class Resp:
            status = 204

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b""

        return Resp()

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        code = bobreport.publish_local_peer_fuel(
            home, mid, force=True, url="https://example.test/bob/v1/report"
        )
    assert code == 204
    assert len(posted) == 1
    body = posted[0]
    assert body.get("weekly_known") is False
    assert body.get("weekly") in (None, "")
    assert bobreport._last_fuel_publish_diag.get("acquisition") == "system-profile-skipped"

