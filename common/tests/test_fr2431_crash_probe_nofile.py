"""FR #2431: crash probe / do-not-file markers must never create intake issues."""
from __future__ import annotations

import json
from pathlib import Path

import crash_report


def test_should_skip_probe_exe_and_do_not_file_message():
    assert crash_report.should_skip_report("probe", RuntimeError("probe-shape-only-do-not-file"))
    assert crash_report.should_skip_report("PROBE", RuntimeError("x"))
    assert crash_report.should_skip_report("bob-worker", RuntimeError("shape probe-shape-only-do-not-file ok"))
    assert crash_report.should_skip_report("jeeves", RuntimeError("please do-not-file this"))
    assert not crash_report.should_skip_report("bob-worker", RuntimeError("real boom"))
    assert not crash_report.should_skip_report("jeeves", ValueError("password=x"))


def test_report_exception_skips_probe_without_post_or_spool(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_CRASH_SPOOL", str(tmp_path / "spool"))
    monkeypatch.setattr(crash_report, "_gh_search_open_sig", lambda *a, **k: None)

    def boom_post(*a, **k):
        raise AssertionError("must not post probe")

    try:
        raise RuntimeError("probe-shape-only-do-not-file")
    except RuntimeError as exc:
        r = crash_report.report_exception(
            "probe", type(exc), exc, exc.__traceback__, filer_post=boom_post
        )
    assert r.get("ok") is True
    assert r.get("skipped") is True
    assert list(Path(crash_report.spool_dir()).glob("crash-*.json")) == []


def test_report_exception_skips_do_not_file_on_real_exe(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_CRASH_SPOOL", str(tmp_path / "spool"))
    monkeypatch.setattr(crash_report, "_gh_search_open_sig", lambda *a, **k: None)

    def boom_post(*a, **k):
        raise AssertionError("must not post")

    try:
        raise RuntimeError("unit-test do-not-file marker")
    except RuntimeError as exc:
        r = crash_report.report_exception(
            "bob-worker", type(exc), exc, exc.__traceback__, filer_post=boom_post
        )
    assert r.get("skipped") is True
    assert list(Path(crash_report.spool_dir()).glob("crash-*.json")) == []


def test_flush_spool_drops_probe_payloads(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_CRASH_SPOOL", str(tmp_path / "spool"))
    spool = crash_report.spool_dir()
    spool.mkdir(parents=True, exist_ok=True)
    path = spool / "crash-99f19bdeaa353456-1.json"
    path.write_text(
        json.dumps(
            {
                "title": "crash: probe RuntimeError 99f19bdeaa353456",
                "body": "exception: RuntimeError: probe-shape-only-do-not-file\ncrash-sig:99f19bdeaa353456",
                "repo": "SimonBarnett/bobiverse",
                "sig": "99f19bdeaa353456",
                "exe": "probe",
            }
        ),
        encoding="utf-8",
    )
    posts = []

    def ok_post(title, body, *, repo, sig, exe):
        posts.append(title)
        return {"ok": True}

    monkeypatch.setattr(crash_report, "_gh_search_open_sig", lambda *a, **k: None)
    stats = crash_report.flush_spool(filer_post=ok_post)
    assert stats["dropped"] >= 1
    assert posts == []
    assert not path.exists()
