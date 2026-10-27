"""FR #5067: airc wedge/crash/abnormal-exit each POST once with dedupe_key."""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
COMMON = Path(__file__).resolve().parents[2] / "common" / "scripts"
for p in (str(SCRIPTS), str(COMMON)):
    if p not in sys.path:
        sys.path.insert(0, p)

import airc_intake_event as ev  # noqa: E402
import crash_report  # noqa: E402


def test_fr5067_auth_wedge_one_dedupe_key(monkeypatch, tmp_path):
    monkeypatch.setenv("BOB_MACHINE_ID", "marchhare")
    posts: list[dict] = []

    def fake_post(title, body, **kw):
        posts.append({"title": title, "body": body, "sig": kw.get("sig")})
        return {"ok": True}

    a = ev.report_airc_event(
        "auth-wedge",
        "channel-state-unknown for 90s",
        home=tmp_path,
        filer_post=fake_post,
    )
    b = ev.report_airc_event(
        "auth-wedge",
        "channel-state-unknown for 91s",
        home=tmp_path,
        filer_post=fake_post,
    )
    assert a.get("ok") is True
    assert a.get("dedupe_key") == "airc|marchhare|auth-wedge"
    assert a["dedupe_key"] == b["dedupe_key"]
    assert all(p["sig"] == "airc|marchhare|auth-wedge" for p in posts)
    assert "channel-state-unknown" in posts[0]["body"]
    assert "machine=`marchhare`" in posts[0]["body"]
    assert "first_seen:" in posts[0]["body"]
    assert "last_seen:" in posts[0]["body"]


def test_fr5067_abnormal_exit_marker(monkeypatch, tmp_path):
    monkeypatch.setenv("BOB_MACHINE_ID", "flamingo")
    posts: list[str] = []

    def fake_post(title, body, **kw):
        posts.append(kw.get("sig") or "")
        return {"ok": True}

    ev.write_stamp(tmp_path, "running")
    r = ev.note_previous_abnormal_exit(tmp_path, filer_post=fake_post)
    assert r and r.get("ok") is True
    assert posts == ["airc|flamingo|abnormal-exit"]
    assert ev.read_stamp(tmp_path) == "running"
    posts.clear()
    ev.mark_clean_exit(tmp_path)
    ev.write_stamp(tmp_path, "running")  # simulate new start after clean? clean then running
    ev.mark_clean_exit(tmp_path)
    r2 = ev.note_previous_abnormal_exit(tmp_path, filer_post=fake_post)
    # previous was clean -> no report
    assert r2 is None
    assert posts == []


def test_fr5067_intake_down_spools(monkeypatch, tmp_path):
    monkeypatch.setenv("BOB_MACHINE_ID", "ionos")
    monkeypatch.setenv("BOB_CRASH_SPOOL", str(tmp_path / "spool"))

    def boom(*_a, **_k):
        raise OSError("intake down")

    r = ev.report_airc_event("names-reconnect", "stage=reconnect", home=tmp_path, filer_post=boom)
    assert r.get("spooled") or r.get("ok") is False
    assert any((tmp_path / "spool").rglob("crash-*.json")) or r.get("spooled")


def test_fr5067_injected_exception_post_sends_dedupe_key(monkeypatch, tmp_path):
    monkeypatch.setenv("BOB_CRASH_REPORT", "1")
    monkeypatch.setenv("BOB_MACHINE_ID", "marchhare")
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

    monkeypatch.setattr(crash_report.urllib.request, "urlopen", fake_urlopen)
    crash_report._post_intake(
        "t",
        "b",
        repo="SimonBarnett/bobiverse",
        sig="airc|marchhare|exception",
        exe="airc",
    )
    assert seen["body"].get("dedupe_key") == "airc|marchhare|exception"


def test_fr5067_service_wires_watchdogs():
    root = Path(__file__).resolve().parents[2]
    src = (root / "airc" / "scripts" / "airc_console_service.py").read_text(encoding="utf-8")
    assert "report_airc_event" in src
    assert "auth-wedge" in src
    assert "names-reconnect" in src
    assert "note_previous_abnormal_exit" in src
    assert "mark_clean_exit" in src or "mark_restarting" in src
