"""FR #2535: skip filing WinError 448 pytest-current noise; do not steal pytest hooks."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import crash_report


def _oserror_448(path: str) -> OSError:
    err = OSError(
        f"[WinError 448] The path cannot be traversed because it contains an untrusted mount point: {path!r}"
    )
    err.winerror = 448
    err.errno = 448
    return err


def test_should_skip_winerror_448_pytest_current_message():
    exc = _oserror_448(r"C:\Users\Administrator\AppData\Local\Temp\pytest-of-Administrator\pytest-current")
    assert crash_report.should_skip_report("jeeves", exc)
    assert crash_report.should_skip_report(
        "bob-worker",
        None,
        body="exception: OSError: [WinError 448] untrusted mount point: pytest-of-Administrator/pytest-current",
    )


def test_should_not_skip_unrelated_oserror_or_real_crash():
    plain = OSError("disk full")
    assert not crash_report.should_skip_report("jeeves", plain)
    other = OSError("[WinError 448] The path cannot be traversed because it contains an untrusted mount point: 'D:\\data\\prod'")
    other.winerror = 448
    assert not crash_report.should_skip_report("jeeves", other)
    assert not crash_report.should_skip_report("jeeves", RuntimeError("real boom"))


def test_report_exception_skips_pytest_untrusted_mount(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_CRASH_SPOOL", str(tmp_path / "spool"))
    monkeypatch.setattr(crash_report, "_gh_search_open_sig", lambda *a, **k: None)

    def boom_post(*a, **k):
        raise AssertionError("must not post pytest WinError 448")

    exc = _oserror_448(r"C:\Temp\pytest-of-Administrator\pytest-current")
    r = crash_report.report_exception(
        "jeeves", type(exc), exc, None, filer_post=boom_post
    )
    assert r.get("ok") is True
    assert r.get("skipped") is True
    assert list(Path(crash_report.spool_dir()).glob("crash-*.json")) == []


def test_install_shipped_exe_noop_under_pytest(monkeypatch):
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_fr2535.py::test_x")
    monkeypatch.delenv("BOB_CRASH_ALLOW_UNDER_PYTEST", raising=False)
    # Reset install state
    crash_report._installed_for = None
    before = sys.excepthook
    try:
        crash_report.install("jeeves", flush=False)
        assert sys.excepthook is before
        assert crash_report._installed_for is None
        # unit-test exe still installs under pytest
        crash_report.install("unit-test-exe", flush=False)
        assert crash_report._installed_for == "unit-test-exe"
        assert sys.excepthook is not before
    finally:
        # MRB #2538: restore process hooks so later tests keep pytest's excepthook.
        sys.excepthook = before
        crash_report._installed_for = None
