"""FR #2541: KeyboardInterrupt / SystemExit are shutdown signals — never file as crashes."""
from __future__ import annotations

from pathlib import Path

import crash_report


def test_fr2541_should_skip_keyboardinterrupt_and_systemexit():
    assert crash_report.should_skip_report("airc", KeyboardInterrupt())
    assert crash_report.should_skip_report("airc", KeyboardInterrupt("stop"))
    assert crash_report.should_skip_report("jeeves", SystemExit(0))
    assert crash_report.should_skip_report("bob-worker", SystemExit(1))
    assert not crash_report.should_skip_report("airc", RuntimeError("real boom"))
    assert not crash_report.should_skip_report("airc", TimeoutError("The read operation timed out"))


def test_fr2541_report_exception_skips_keyboardinterrupt(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_CRASH_SPOOL", str(tmp_path / "spool"))
    monkeypatch.setattr(crash_report, "_gh_search_open_sig", lambda *a, **k: None)

    def boom_post(*a, **k):
        raise AssertionError("must not post KeyboardInterrupt")

    try:
        raise KeyboardInterrupt()
    except KeyboardInterrupt as exc:
        r = crash_report.report_exception(
            "airc", type(exc), exc, exc.__traceback__, filer_post=boom_post
        )
    assert r.get("ok") is True
    assert r.get("skipped") is True
    assert list(Path(crash_report.spool_dir()).glob("crash-*.json")) == []


def test_fr2541_source_gates():
    src = Path(crash_report.__file__).read_text(encoding="utf-8")
    assert "FR #2541" in src
    assert "KeyboardInterrupt" in src
    assert "SystemExit" in src
