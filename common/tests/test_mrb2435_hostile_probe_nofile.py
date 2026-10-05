"""Hostile MRB #2435: probe / do-not-file must not file; real crashes still can."""
from __future__ import annotations

import json
from pathlib import Path

import crash_report


def test_crash_probe_alias_exe_skipped():
    assert crash_report.should_skip_report("crash-probe", RuntimeError("x"))
    assert crash_report.should_skip_report("crash_probe", RuntimeError("x"))


def test_flush_drops_do_not_file_body_even_when_exe_real(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_CRASH_SPOOL", str(tmp_path / "spool"))
    spool = crash_report.spool_dir()
    spool.mkdir(parents=True, exist_ok=True)
    path = spool / "crash-deadbeef-1.json"
    path.write_text(
        json.dumps(
            {
                "title": "crash: bob-worker RuntimeError deadbeef",
                "body": "probe-shape-only-do-not-file leftover spool",
                "repo": "SimonBarnett/bobiverse",
                "sig": "deadbeef",
                "exe": "bob-worker",
            }
        ),
        encoding="utf-8",
    )
    posts = []

    def ok_post(title, body, *, repo, sig, exe):
        posts.append(exe)
        return {"ok": True}

    monkeypatch.setattr(crash_report, "_gh_search_open_sig", lambda *a, **k: None)
    stats = crash_report.flush_spool(filer_post=ok_post)
    assert stats["dropped"] >= 1
    assert posts == []
    assert not path.exists()


def test_real_crash_still_posts(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_CRASH_SPOOL", str(tmp_path / "spool"))
    monkeypatch.setattr(crash_report, "_gh_search_open_sig", lambda *a, **k: None)
    seen = {}

    def ok_post(title, body, *, repo, sig, exe):
        seen.update(title=title, exe=exe)
        return {"ok": True}

    try:
        raise RuntimeError("production-path boom")
    except RuntimeError as exc:
        r = crash_report.report_exception(
            "jeeves", type(exc), exc, exc.__traceback__, filer_post=ok_post
        )
    assert r.get("ok") is True
    assert not r.get("skipped")
    assert seen.get("exe") == "jeeves"
    assert "production-path" in seen["title"] or "jeeves" in seen["title"]
