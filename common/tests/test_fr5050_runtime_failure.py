"""FR #5050: injected tray / ear / Jeeves failures produce exactly one intake."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import runtime_failure  # noqa: E402


def _inject(component: str, monkeypatch, tmp_path):
    posts: list[tuple[str, str]] = []

    def fake_post(title, body, **kw):
        posts.append((title, body))
        return {"ok": True, "intake_id": "in_test"}

    monkeypatch.setenv("BOB_RUNTIME_FAILURE_DIR", str(tmp_path / "rf"))
    monkeypatch.setenv("BOB_CRASH_SPOOL", str(tmp_path / "spool"))
    runtime_failure._SEEN.clear()
    exc = RuntimeError("injected-webhook-fail")
    a = runtime_failure.report(component, exc, site="timer", filer_post=fake_post, rate_s=3600)
    b = runtime_failure.report(component, exc, site="timer", filer_post=fake_post, rate_s=3600)
    return posts, a, b


def test_fr5050_tray_injected_failure_one_intake(monkeypatch, tmp_path):
    posts, a, b = _inject("tray", monkeypatch, tmp_path)
    assert a.get("ok") is True
    assert b.get("deduped") is True
    assert len(posts) == 1
    title, body = posts[0]
    assert "tray" in title
    assert "first_seen:" in body
    assert "last_seen:" in body
    assert "machine=" in body
    assert "version=" in body


def test_fr5050_ear_injected_failure_one_intake(monkeypatch, tmp_path):
    posts, _a, b = _inject("bob-ear", monkeypatch, tmp_path)
    assert b.get("deduped") is True
    assert len(posts) == 1
    assert "bob-ear" in posts[0][0]


def test_fr5050_jeeves_injected_failure_one_intake(monkeypatch, tmp_path):
    posts, _a, b = _inject("jeeves", monkeypatch, tmp_path)
    assert b.get("deduped") is True
    assert len(posts) == 1
    assert "jeeves" in posts[0][0]


def test_fr5050_intake_down_spools(monkeypatch, tmp_path):
    monkeypatch.setenv("BOB_RUNTIME_FAILURE_DIR", str(tmp_path / "rf"))
    monkeypatch.setenv("BOB_CRASH_SPOOL", str(tmp_path / "spool"))
    runtime_failure._SEEN.clear()

    def boom(*_a, **_k):
        raise OSError("intake down")

    r = runtime_failure.report(
        "tray", RuntimeError("timer"), site="digest", filer_post=boom
    )
    assert r.get("spooled") or r.get("ok") is False
    spool = tmp_path / "spool"
    assert any(spool.rglob("crash-*.json")) or r.get("spooled")


def test_fr5050_mrb5051_post_intake_sends_dedupe_key(monkeypatch, tmp_path):
    """Hostile: AC requires intake dedupe_key (#4963), not idempotency alone."""
    import crash_report
    import json
    seen = {}

    class FakeResp:
        status = 202

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"ok":true,"intake_id":"in_x"}'

    def fake_urlopen(req, timeout=0):
        seen["body"] = json.loads(req.data.decode("utf-8"))
        return FakeResp()

    monkeypatch.setenv("BOB_CRASH_REPORT", "1")
    monkeypatch.setattr(crash_report.urllib.request, "urlopen", fake_urlopen)
    crash_report._post_intake("t", "b", repo="SimonBarnett/bobiverse", sig="tray|timer|x", exe="tray")
    assert seen["body"].get("dedupe_key") == "tray|timer|x"
    assert seen["body"].get("idempotency_key", "").startswith("crash-")
