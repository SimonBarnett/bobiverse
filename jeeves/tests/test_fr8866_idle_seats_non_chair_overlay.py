"""FR #8866: idle_seats non-chair live /report overlay."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from repo_layout import REPO

MONITOR = REPO / "jeeves" / "tools" / "monitor"
sys.path.insert(0, str(MONITOR))

import _common as common  # noqa: E402
import auto_feed  # noqa: E402
import idle_seats  # noqa: E402


def _fresh_report(**extra):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc = {
        "ts": ts,
        "chairNick": "Jeeves",
        "queue": {
            "unaccepted": [{"id": 1, "task": "FR", "repo": "SimonBarnett/bobiverse"}],
            "accepted": [],
            "offerable_count": 69,
        },
        "machines": {
            "marchhare": {
                "workers": {
                    "7472": {"state": "idle", "nick": "marchhare-7472", "pid": "7472"},
                }
            }
        },
    }
    doc.update(extra)
    return doc


def _args(chair: Path, digest: Path):
    return SimpleNamespace(chair_home=str(chair), digest_home=str(digest), dry_run=False)


def _homes(tmp_path: Path):
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    digest.mkdir()
    return chair, digest


def test_live_idle_with_eligible_row_exits_1(tmp_path, monkeypatch):
    chair, digest = _homes(tmp_path)
    monkeypatch.setattr(common, "fetch_live_report", lambda **_k: _fresh_report())
    payload, code = idle_seats.check(_args(chair, digest))
    assert code == common.EXIT_FINDING
    assert payload["source"] == "live_report"
    assert payload["offerable_estimate"] is True
    assert payload["idle_seats"][0]["nick"] == "marchhare-7472"
    assert payload["offerable_for_live_seats"] == 1
    assert "marchhare-7472" in payload["findings"][0]
    assert "live report" in payload["findings"][0]
    assert not (digest / "digest.json").exists()
    assert not (chair / "queue.json").exists()


def test_no_idle_workers_exits_0_without_local_files(tmp_path, monkeypatch):
    chair, digest = _homes(tmp_path)
    doc = _fresh_report()
    doc["machines"] = {"marchhare": {"workers": {}}}
    monkeypatch.setattr(common, "fetch_live_report", lambda **_k: doc)
    payload, code = idle_seats.check(_args(chair, digest))
    assert code == common.EXIT_OK
    assert payload["idle_seats"] == []
    assert payload["ok"] is True
    assert any("estimate" in n for n in payload["notes"])


def test_pending_needs_human_and_other_pin_exit_0(tmp_path, monkeypatch):
    chair, digest = _homes(tmp_path)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc = _fresh_report()
    doc["queue"]["unaccepted"] = [
        {"id": 1, "offered_to": "marchhare-1", "offered_ts": now},
        {"id": 2, "needs_human": True},
        {"id": 3, "require_machine": "walrus"},
    ]
    monkeypatch.setattr(common, "fetch_live_report", lambda **_k: doc)
    payload, code = idle_seats.check(_args(chair, digest))
    assert code == common.EXIT_OK
    assert payload["offerable_for_live_seats"] == 0
    assert payload["healthy_idle_empty_offerable"] is True


def test_pin_to_idle_machine_exits_1(tmp_path, monkeypatch):
    chair, digest = _homes(tmp_path)
    doc = _fresh_report()
    doc["queue"]["unaccepted"] = [{"id": 9, "require_machine": "MarchHare"}]
    monkeypatch.setattr(common, "fetch_live_report", lambda **_k: doc)
    payload, code = idle_seats.check(_args(chair, digest))
    assert code == common.EXIT_FINDING
    assert payload["offerable_for_live_seats"] == 1


def test_unusable_report_exits_1(tmp_path, monkeypatch):
    chair, digest = _homes(tmp_path)
    cases = [
        None,
        _fresh_report(ts="2020-01-01T00:00:00Z"),
        _fresh_report(stale=True),
        _fresh_report(machines=[]),
        {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "machines": {}, "queue": {}},
    ]
    for doc in cases:
        def _fetch(_doc=doc, **_k):
            return _doc

        monkeypatch.setattr(common, "fetch_live_report", _fetch)
        payload, code = idle_seats.check(_args(chair, digest))
        assert code == common.EXIT_FINDING, doc
        assert payload["idle_seats"] == []
        assert any("live report unavailable" in f for f in payload["findings"])


def test_workers_stale_ignored(tmp_path, monkeypatch):
    chair, digest = _homes(tmp_path)
    doc = _fresh_report()
    doc["machines"]["marchhare"]["workers_stale"] = True
    monkeypatch.setattr(common, "fetch_live_report", lambda **_k: doc)
    payload, code = idle_seats.check(_args(chair, digest))
    assert code == common.EXIT_OK
    assert payload["idle_seats"] == []
    assert any("workers_stale" in n for n in payload["notes"])


def test_local_queue_does_not_fetch(tmp_path, monkeypatch):
    chair, digest = _homes(tmp_path)
    (digest / "queue.json").write_text('{"unaccepted":[]}\n', encoding="utf-8")
    (digest / "digest.json").write_text('{"machines":{}}\n', encoding="utf-8")
    called = {"n": 0}

    def _boom(**_k):
        called["n"] += 1
        raise AssertionError("fetch")

    monkeypatch.setattr(common, "fetch_live_report", _boom)
    payload, code = idle_seats.check(_args(chair, digest))
    assert called["n"] == 0
    assert code == common.EXIT_OK
    assert payload.get("source") != "live_report"


def test_auto_feed_alerts_on_live_idle(tmp_path, monkeypatch):
    chair, digest = _homes(tmp_path)
    monkeypatch.setattr(common, "fetch_live_report", lambda **_k: _fresh_report())
    doc, code = auto_feed.check(_args(chair, digest))
    assert code == common.EXIT_FINDING
    text = " ".join(doc["findings"])
    assert "auto-feed off" in text
    assert "marchhare-7472" not in text or "idle" in text
    assert "offerable" in text
