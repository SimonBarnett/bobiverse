"""FR #7504: stale fleet Copilot/OpenCode Go (2 min) reports as exception; dedupe + recovery."""
from __future__ import annotations

from pathlib import Path

import bobreport
import fleet_pool_fetch as fp


NOW = 1_700_000_000.0
STALE = NOW + 130.0  # > 120s


def _home(tmp: Path) -> Path:
    home = tmp / "home"
    home.mkdir()
    bobreport.save_digest(home, bobreport.empty_digest())
    return home


def test_fr7504_stale_threshold_constant():
    assert fp.FLEET_POOL_STALE_S == 120.0


def test_fr7504_stale_two_minutes_files_one_report(tmp_path: Path, monkeypatch):
    home = _home(tmp_path)
    filed: list[dict] = []

    def fake_file(**kw):
        filed.append(dict(kw))
        return {"ok": True, "number": 9001, "deduped": False}

    monkeypatch.setattr(fp, "file_fleet_pool_stale_exception", fake_file)
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
    # digest last-good
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
    body = filed[0]["body"]
    assert "copilot" in body.lower() or fp.POOL_COPILOT in body
    assert "2026-11-15T14:00:00Z" in body
    assert "provider-http-500" in body
    assert "jeeves" in body.lower() or "version" in body.lower()
    # no secret-shaped blobs
    assert "ghp_" not in body
    assert "Bearer " not in body
    assert filed[0]["pool"] == fp.POOL_COPILOT

    # still stale: no second file
    out2 = fp.maybe_report_fleet_pool_staleness(home, now=STALE + 10)
    assert out2[fp.POOL_COPILOT]["action"] in ("deduped", "commented", "skipped")
    assert len(filed) == 1


def test_fr7504_recovery_comments_does_not_close(tmp_path: Path, monkeypatch):
    home = _home(tmp_path)
    comments: list[dict] = []

    def fake_comment(**kw):
        comments.append(dict(kw))
        return True

    monkeypatch.setattr(fp, "comment_fleet_pool_stale_issue", fake_comment)
    monkeypatch.setattr(
        fp,
        "file_fleet_pool_stale_exception",
        lambda **k: (_ for _ in ()).throw(AssertionError("must not file on recovery")),
    )

    state = {
        fp.POOL_OC_GO: {
            "last_ok": STALE,  # fresh again
            "last_attempt": STALE,
            "error": None,
            "fail_streak": 0,
            "stale_issue": 4242,
            "stale_open": True,
        }
    }
    fp._save_state(home, state)
    out = fp.maybe_report_fleet_pool_staleness(home, now=STALE + 5)
    assert out[fp.POOL_OC_GO]["action"] == "recovered"
    assert len(comments) == 1
    assert "recover" in comments[0]["body"].lower()
    # still recorded open (no auto-close)
    st = fp._load_state(home)[fp.POOL_OC_GO]
    assert st.get("stale_issue") == 4242
    assert st.get("stale_open") is False or st.get("stale_recovered") is True


def test_fr7504_tick_invokes_stale_check(tmp_path: Path, monkeypatch):
    home = _home(tmp_path)
    hits: list[float] = []

    def fake_maybe(home_arg, *, now=None, **_k):
        hits.append(float(now if now is not None else 0))
        return {}

    monkeypatch.setattr(fp, "maybe_report_fleet_pool_staleness", fake_maybe)
    monkeypatch.setattr(
        fp,
        "fetch_copilot_default",
        lambda *_a, **_k: {
            "id": fp.POOL_COPILOT,
            "fresh": True,
            "remaining": 50,
            "fetched_at": "2026-11-15T14:00:00Z",
            "source": "copilot_internal/user",
        },
    )
    monkeypatch.setattr(
        fp,
        "fetch_opencode_default",
        lambda *_a, **_k: {
            fp.POOL_OC_GO: {
                "id": fp.POOL_OC_GO,
                "fresh": True,
                "remaining": 10,
                "fetched_at": "2026-11-15T14:00:00Z",
                "source": "go-zen-usage",
            }
        },
    )
    fp.tick_fleet_pools(home, now=NOW, force=True)
    assert hits == [NOW]
