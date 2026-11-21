"""MRB #8673 hostile: private fleet-cursor-private.json + public digest omit."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import fleet_pool_fetch as fpf


def _iso(now: float) -> str:
    return (
        datetime.fromtimestamp(now, timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def test_mrb8673_private_cursor_name_and_write_strips_secrets(tmp_path: Path):
    assert fpf.PRIVATE_CURSOR_NAME == "fleet-cursor-private.json"
    now = 1_700_000_000.0
    fpf.write_private_cursor_meter(
        tmp_path,
        {
            "remaining": 0,
            "fresh": True,
            "fetched_at": _iso(now),
            "source": "credman:hidden",
        },
    )
    loaded = fpf.load_private_cursor_meter(tmp_path)
    assert loaded is not None
    assert loaded["remaining"] == 0
    assert "credman" not in str(loaded.get("source") or "").lower()


def test_mrb8673_tick_keeps_public_digest_cursor_free(tmp_path: Path, monkeypatch):
    now = 1_700_000_000.0

    def fake_cursor(home, n):
        return {
            "id": "cursor",
            "remaining": 0,
            "fetched_at": _iso(n),
            "last_attempt_at": _iso(n),
            "error": None,
            "source": "credman:x",
            "fresh": True,
        }

    monkeypatch.setattr(fpf, "fetch_copilot_default", lambda h, n: fpf.empty_meter(pool_id="copilot", source="t", now=n))
    monkeypatch.setattr(fpf, "fetch_opencode_default", lambda h, n: {})
    monkeypatch.setattr(fpf, "pool_due", lambda *a, **k: True)
    fpf.tick_fleet_pools(tmp_path, now=now, fetch_cursor=fake_cursor)
    import json
    digest = json.loads((tmp_path / "digest.json").read_text(encoding="utf-8"))
    assert "cursor" not in (digest.get("fleet_pools") or {})
    priv = fpf.load_private_cursor_meter(tmp_path)
    assert priv is not None and priv["remaining"] == 0
