"""FR #8579: non-chair monitor soft-pass when live /report is fresh."""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from repo_layout import REPO

MONITOR = REPO / "jeeves" / "tools" / "monitor"
sys.path.insert(0, str(MONITOR))

import _common as common  # noqa: E402
import health  # noqa: E402
import queue_flow  # noqa: E402
import stale_digest  # noqa: E402
import stuck_accepted  # noqa: E402


def _fresh_report(**extra):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc = {
        "ts": ts,
        "chairNick": "Jeeves",
        "queue": {"unaccepted": [{"id": 1}, {"id": 2}], "accepted": [{"id": 9}]},
        "machines": {"redqueen": {"workers": {}}},
    }
    doc.update(extra)
    return doc


def _args(chair: Path, digest: Path):
    return SimpleNamespace(chair_home=str(chair), digest_home=str(digest), dry_run=False)


def test_live_report_is_fresh_and_stale():
    fresh = _fresh_report()
    assert common.live_report_is_fresh(fresh) is True
    old = dict(fresh)
    old["ts"] = "2020-01-01T00:00:00Z"
    assert common.live_report_is_fresh(old) is False
    assert common.live_report_is_fresh(None) is False


def test_non_chair_overlay_requires_missing_queue(tmp_path, monkeypatch):
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    digest.mkdir()
    monkeypatch.setattr(common, "fetch_live_report", lambda **_k: _fresh_report())

    assert common.non_chair_overlay(chair, digest, require_missing_queue=True) is not None

    (chair / "queue.json").write_text('{"unaccepted":[]}\n', encoding="utf-8")
    assert common.non_chair_overlay(chair, digest, require_missing_queue=True) is None


def test_health_soft_passes_when_non_chair_and_report_fresh(tmp_path, monkeypatch):
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    digest.mkdir()

    monkeypatch.setattr(health, "_service_state", lambda name: "missing")
    monkeypatch.setattr(health, "_service_start_type", lambda name: "Automatic")
    monkeypatch.setattr(health, "_bobcallback_ok", lambda: ("missing/task:missing", False))
    monkeypatch.setattr(common, "fetch_live_report", lambda **_k: _fresh_report())

    payload, code = health.check(_args(chair, digest))
    assert code == common.EXIT_OK
    assert payload["ok"] is True
    assert payload.get("non_chair_overlay") is True
    assert payload["findings"] == []
    assert any("non-chair soft-ok" in n for n in payload["notes"])



def test_health_ok_path_no_unbound_overlay(tmp_path, monkeypatch):
    """MRB #8586: findings-empty must not raise UnboundLocalError on overlay."""
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    digest.mkdir()
    (chair / "queue.json").write_text('{"unaccepted":[]}\n', encoding="utf-8")

    monkeypatch.setattr(health, "_service_state", lambda name: "running")
    monkeypatch.setattr(health, "_service_start_type", lambda name: "Automatic")
    monkeypatch.setattr(health, "_bobcallback_ok", lambda: ("listen:7700", True))

    payload, code = health.check(_args(chair, digest))
    assert code == common.EXIT_OK
    assert payload["ok"] is True
    assert payload["findings"] == []
    assert "non_chair_overlay" not in payload


def test_health_still_finds_when_queue_present(tmp_path, monkeypatch):
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    digest.mkdir()
    (chair / "queue.json").write_text('{"unaccepted":[]}\n', encoding="utf-8")

    monkeypatch.setattr(health, "_service_state", lambda name: "missing")
    monkeypatch.setattr(health, "_service_start_type", lambda name: "Automatic")
    monkeypatch.setattr(health, "_bobcallback_ok", lambda: ("missing/task:missing", False))
    monkeypatch.setattr(common, "fetch_live_report", lambda **_k: _fresh_report())

    payload, code = health.check(_args(chair, digest))
    assert code == common.EXIT_FINDING
    assert payload["ok"] is False
    assert any("ircJeeves" in f for f in payload["findings"])


def test_queue_flow_soft_passes_missing_queue(tmp_path, monkeypatch):
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    digest.mkdir()
    monkeypatch.setattr(common, "fetch_live_report", lambda **_k: _fresh_report())

    payload, code = queue_flow.check(_args(chair, digest))
    assert code == common.EXIT_OK
    assert payload["ok"] is True
    assert payload.get("non_chair_overlay") is True
    assert payload.get("live_queue_unaccepted") == 2


def test_stuck_accepted_soft_passes_missing_queue(tmp_path, monkeypatch):
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    digest.mkdir()
    monkeypatch.setattr(common, "fetch_live_report", lambda **_k: _fresh_report())

    payload, code = stuck_accepted.check(_args(chair, digest))
    assert code == common.EXIT_OK
    assert payload["ok"] is True
    assert payload.get("non_chair_overlay") is True


def test_stale_digest_soft_passes_old_local_digest(tmp_path, monkeypatch):
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    digest.mkdir()
    path = digest / "digest.json"
    path.write_text(json.dumps({"ts": "2020-01-01T00:00:00Z"}), encoding="utf-8")
    # Force ancient mtime as well
    old = time.time() - 3_000_000
    import os

    os.utime(path, (old, old))
    monkeypatch.setattr(common, "fetch_live_report", lambda **_k: _fresh_report())

    payload, code = stale_digest.check(_args(chair, digest))
    assert code == common.EXIT_OK
    assert payload["ok"] is True
    assert payload.get("non_chair_overlay") is True
    assert payload["findings"] == []


def test_stale_digest_finds_when_report_stale_too(tmp_path, monkeypatch):
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    digest.mkdir()
    path = digest / "digest.json"
    path.write_text(json.dumps({"ts": "2020-01-01T00:00:00Z"}), encoding="utf-8")
    old = time.time() - 3_000_000
    import os

    os.utime(path, (old, old))
    stale_rep = _fresh_report()
    stale_rep["ts"] = "2020-01-01T00:00:00Z"
    monkeypatch.setattr(common, "fetch_live_report", lambda **_k: stale_rep)

    payload, code = stale_digest.check(_args(chair, digest))
    assert code == common.EXIT_FINDING
    assert payload["ok"] is False


def test_start_jeeves_monitor_mentions_non_chair_warn():
    text = (REPO / "jeeves" / "scripts" / "Start-JeevesMonitor.ps1").read_text(encoding="utf-8")
    assert "FR #8579" in text
    assert "chairProbe" in text
    skill = (REPO / "jeeves" / ".grok" / "skills" / "monitor-start" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "FR #8579" in skill
    assert "non_chair_overlay" in skill or "non-chair" in skill.lower()
