"""MRB #2543 hostile gates for FR #2541 KeyboardInterrupt / SystemExit crash skip."""
from __future__ import annotations

import json
from pathlib import Path

import crash_report


def test_mrb2543_should_skip_exc_and_body_title():
    assert crash_report.should_skip_report("airc", KeyboardInterrupt())
    assert crash_report.should_skip_report("jeeves", SystemExit(0))
    assert crash_report.should_skip_report(
        "airc",
        None,
        body="exception: KeyboardInterrupt\ncrash-sig:6b485fc97e52813b",
        title="crash: airc KeyboardInterrupt 6b485fc97e52813b",
    )
    assert crash_report.should_skip_report(
        "bob-worker", None, body="exception: SystemExit: 1"
    )
    assert not crash_report.should_skip_report("airc", TimeoutError("The read operation timed out"))
    assert not crash_report.should_skip_report("airc", RuntimeError("real boom"))


def test_mrb2543_flush_spool_drops_keyboardinterrupt_body(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_CRASH_SPOOL", str(tmp_path / "spool"))
    spool = crash_report.spool_dir()
    spool.mkdir(parents=True, exist_ok=True)
    path = spool / "crash-6b485fc97e52813b-1.json"
    path.write_text(
        json.dumps(
            {
                "title": "crash: airc KeyboardInterrupt 6b485fc97e52813b",
                "body": "exception: KeyboardInterrupt\ncrash-sig:6b485fc97e52813b",
                "repo": "SimonBarnett/bobiverse",
                "sig": "6b485fc97e52813b",
                "exe": "airc",
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


def test_mrb2543_airc_source_gates_keyboardinterrupt():
    src = Path("airc/scripts/airc_console_service.py").read_text(encoding="utf-8")
    assert "FR #2541" in src
    assert src.count("except KeyboardInterrupt") >= 2
    assert "_check_probe_timeout" in src
