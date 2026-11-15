"""FR #7518: locked topics replace retries, then one exception report."""
from __future__ import annotations

import os
from pathlib import Path

import priority_customer as pc


def _chair(tmp_path: Path, monkeypatch) -> Path:
    chair = tmp_path / ".jeeves"
    chair.mkdir()
    monkeypatch.setenv("BOB_HOME", str(chair))
    monkeypatch.delenv("BOB_DIGEST_HOME", raising=False)
    return chair


def test_fr7518_locked_replace_retries_then_succeeds(tmp_path: Path, monkeypatch):
    chair = _chair(tmp_path, monkeypatch)
    pc.save_topic_repos(chair, ["acme/keep"])
    real = os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        if not str(dst).endswith("priority-customer-topics.json"):
            return real(src, dst)
        calls["n"] += 1
        if calls["n"] < 3:
            err = PermissionError(13, "Access is denied")
            err.winerror = 5  # type: ignore[attr-defined]
            raise err
        return real(src, dst)

    monkeypatch.setattr(os, "replace", flaky)
    monkeypatch.setattr(pc.time, "sleep", lambda _s: None)
    pc.save_topic_repos(chair, ["acme/next"])
    assert calls["n"] == 3
    assert pc.load_topic_repos(chair) == {"acme/next"}
    assert pc.last_topics_write_status().get("ok") is True


def test_fr7518_persistent_lock_reports_once_and_keeps_last(tmp_path: Path, monkeypatch):
    chair = _chair(tmp_path, monkeypatch)
    pc.save_topic_repos(chair, ["acme/keep"])
    reports: list[str] = []

    real = os.replace

    def always_locked(src, dst):
        if not str(dst).endswith("priority-customer-topics.json"):
            return real(src, dst)
        err = PermissionError(13, "Access is denied")
        err.winerror = 5  # type: ignore[attr-defined]
        raise err

    def _report(exe, exc_type, exc_value, tb, **kwargs):
        reports.append(str(getattr(exc_type, "__name__", exc_type)))
        return {"ok": True}

    import crash_report

    monkeypatch.setattr(os, "replace", always_locked)
    monkeypatch.setattr(pc.time, "sleep", lambda _s: None)
    monkeypatch.setattr(crash_report, "report_exception", _report)
    kept = pc.refresh_topic_repos(
        chair,
        fetch_json=lambda _u: {"items": [{"full_name": "acme/new"}]},
    )
    assert kept == {"acme/keep"}
    assert pc.load_topic_repos(chair) == {"acme/keep"}
    assert reports == ["PermissionError"]
    assert pc.last_topics_write_status().get("ok") is False


def test_fr7518_stale_tmp_does_not_block_write(tmp_path: Path, monkeypatch):
    chair = _chair(tmp_path, monkeypatch)
    pc.save_topic_repos(chair, ["acme/keep"])
    dest = pc.topics_cache_path(chair)
    stale = dest.with_name(dest.name + ".111.deadbeef.tmp")
    stale.write_text("not json\n", encoding="utf-8")
    pc.save_topic_repos(chair, ["acme/fresh"])
    assert pc.load_topic_repos(chair) == {"acme/fresh"}
    assert not stale.exists()
    assert list(dest.parent.glob(dest.name + ".*.tmp")) == []
