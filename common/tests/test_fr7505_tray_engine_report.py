"""FR #7505: tray engine dead / relaunch-fail -> one report; repeats comment; recovery comments."""
from __future__ import annotations

import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import tray_engine_report as ter  # noqa: E402


def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("BOB_TRAY_ENGINE_REPORT_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("BOB_CRASH_SPOOL", str(tmp_path / "spool"))
    monkeypatch.setenv("BOB_MACHINE_ID", "testbox")
    monkeypatch.setenv("BOB_CRASH_REPORT", "1")
    life = tmp_path / "tray-lifecycle.log"
    life.write_text(
        '{"ts":"t1","event":"engine-stale"}\n'
        '{"ts":"t2","event":"engine-launch","err":"password=SECRET"}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("BOB_TRAY_LIFECYCLE_LOG", str(life))
    return life


def test_fr7505_engine_exit_one_report(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    posts: list[tuple[str, str]] = []
    comments: list[tuple[int, str]] = []

    def filer_new(title, body, **kw):
        posts.append((title, body))
        return {"ok": True, "number": 9001}

    def find_open(repo, sig):
        return None if not comments and not posts else 9001

    def filer_comment(repo, number, body):
        comments.append((number, body))
        return True

    a = ter.report(
        "dead",
        machine="testbox",
        version="2.0.0",
        exit_code="1",
        filer_new=filer_new,
        filer_comment=filer_comment,
        find_open=lambda r, s: None,
        force_comment=True,
    )
    b = ter.report(
        "dead",
        machine="testbox",
        version="2.0.0",
        exit_code="1",
        filer_new=filer_new,
        filer_comment=filer_comment,
        find_open=lambda r, s: 9001,
        force_comment=True,
    )
    assert a.get("deduped") is False
    assert len(posts) == 1
    assert "crash-sig:" in posts[0][1]
    assert "machine=`testbox`" in posts[0][1]
    assert "tray_version=`2.0.0`" in posts[0][1]
    assert "exit_code: 1" in posts[0][1]
    assert "engine-stale" in posts[0][1]
    assert "SECRET" not in posts[0][1]  # redacted
    assert b.get("deduped") is True
    assert len(posts) == 1
    assert len(comments) == 1
    assert comments[0][0] == 9001


def test_fr7505_relaunch_fail_logs_and_reports(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    posts: list[tuple[str, str]] = []

    def filer_new(title, body, **kw):
        posts.append((title, body))
        return {"ok": True, "number": 42}

    r = ter.report(
        "relaunch-fail",
        machine="testbox",
        relaunch_error="StartEngine missing script",
        filer_new=filer_new,
        find_open=lambda r, s: None,
    )
    assert r.get("ok") is True
    assert r.get("deduped") is False
    assert len(posts) == 1
    assert "relaunch-fail" in posts[0][0]
    assert "StartEngine missing script" in posts[0][1]
    assert ter.stable_sig("testbox") == ter.stable_sig("TESTBOX")


def test_fr7505_repeats_comment_not_new_issue(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    posts: list = []
    comments: list = []

    def filer_new(title, body, **kw):
        posts.append(title)
        return {"ok": True, "number": 7}

    ter.report(
        "status-stale",
        machine="testbox",
        filer_new=filer_new,
        find_open=lambda r, s: None,
    )
    for _ in range(3):
        ter.report(
            "status-stale",
            machine="testbox",
            filer_new=filer_new,
            filer_comment=lambda repo, n, b: comments.append(n) or True,
            find_open=lambda r, s: 7,
            force_comment=True,
        )
    assert len(posts) == 1
    assert len(comments) == 3
    assert all(n == 7 for n in comments)


def test_fr7505_recovery_comments_open_issue(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    comments: list[str] = []
    r = ter.report(
        "recovery",
        machine="testbox",
        find_open=lambda r, s: 55,
        filer_comment=lambda repo, n, b: comments.append(b) or True,
        filer_new=lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not open")),
    )
    assert r.get("recovery") is True
    assert r.get("deduped") is True
    assert len(comments) == 1
    assert "recovery" in comments[0]


def test_fr7505_status_stale_threshold(tmp_path):
    snap = tmp_path / "tray-status.json"
    snap.write_text("{}", encoding="utf-8")
    old = time.time() - 200
    import os

    os.utime(snap, (old, old))
    assert ter.maybe_status_stale(snap, stale_s=120) is True
    os.utime(snap, (time.time(), time.time()))
    assert ter.maybe_status_stale(snap, stale_s=120) is False
