"""FR #7391: priority-customer topics cache under Jeeves chair state (SYSTEM-writable)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import bobreport
import priority_customer as pc


def test_fr7391_cache_path_under_chair_not_digest(tmp_path: Path, monkeypatch):
    chair = tmp_path / ".jeeves"
    chair.mkdir()
    digest = tmp_path / "digest-home"
    digest.mkdir()
    monkeypatch.setenv("BOB_HOME", str(chair))
    monkeypatch.setenv("BOB_DIGEST_HOME", str(digest))
    path = pc.topics_cache_path(chair)
    assert path.parent == chair.resolve() or path.parent == chair
    assert "digest-home" not in str(path)
    assert path.name == "priority-customer-topics.json"


def test_fr7391_atomic_write_replaces(tmp_path: Path, monkeypatch):
    chair = tmp_path / ".jeeves"
    chair.mkdir()
    monkeypatch.setenv("BOB_HOME", str(chair))
    monkeypatch.delenv("BOB_DIGEST_HOME", raising=False)
    pc.save_topic_repos(chair, ["acme/one"])
    dest = pc.topics_cache_path(chair)
    assert dest.is_file()
    assert pc.load_topic_repos(chair) == {"acme/one"}
    pc.save_topic_repos(chair, ["acme/two", "acme/three"])
    assert pc.load_topic_repos(chair) == {"acme/two", "acme/three"}
    assert list(dest.parent.glob("*.tmp")) == []
    st = pc.last_topics_write_status()
    assert st.get("ok") is True
    assert str(dest) in str(st.get("path") or "")


def test_fr7391_write_denied_keeps_last_and_health(tmp_path: Path, monkeypatch, caplog):
    chair = tmp_path / ".jeeves"
    chair.mkdir()
    monkeypatch.setenv("BOB_HOME", str(chair))
    digest = tmp_path / "digest-home"
    digest.mkdir()
    monkeypatch.setenv("BOB_DIGEST_HOME", str(digest))
    bobreport.save_digest(digest, bobreport.empty_digest())
    pc.save_topic_repos(chair, ["acme/keep"])

    real_write = Path.write_text

    def boom(self, *a, **k):
        name = Path(self).name
        # Only the topics cache temp (…topics.json.<pid>.<hex>.tmp), not health/digest temps.
        if name.startswith("priority-customer-topics.json.") and name.endswith(".tmp"):
            raise PermissionError("Access is denied")
        return real_write(self, *a, **k)

    monkeypatch.setattr(Path, "write_text", boom)
    caplog.set_level(logging.WARNING)
    kept = pc.refresh_topic_repos(
        chair,
        fetch_json=lambda _u: {"items": [{"full_name": "acme/new"}]},
    )
    assert kept == {"acme/keep"}
    st = pc.last_topics_write_status()
    assert st.get("ok") is False
    assert "Access" in str(st.get("error") or "") or "denied" in str(st.get("error") or "").lower()
    assert st.get("path")
    assert "priority-customer topics cache write failed" in caplog.text
    assert str(st.get("path")) in caplog.text
    doc = bobreport.load_digest(digest)
    health = doc.get("health") or {}
    warn = health.get("priority_customer_topics") or {}
    assert warn.get("ok") is False
    assert warn.get("path")
