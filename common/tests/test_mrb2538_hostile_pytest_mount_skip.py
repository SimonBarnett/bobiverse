"""MRB #2538 hostile: pytest WinError 448 skip + install-under-pytest gates (FR #2535)."""
from __future__ import annotations

import os
import sys

import crash_report


def _oserror_448(path: str) -> OSError:
    err = OSError(
        f"[WinError 448] The path cannot be traversed because it contains an untrusted mount point: {path!r}"
    )
    err.winerror = 448
    return err


def test_mrb2538_pytest_of_without_untrusted_does_not_skip():
    exc = OSError(r"permission denied: C:\Temp\pytest-of-Administrator\pytest-current")
    assert not crash_report.should_skip_report("jeeves", exc)


def test_mrb2538_allow_under_pytest_override(monkeypatch):
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_mrb2538.py::test_x")
    monkeypatch.setenv("BOB_CRASH_ALLOW_UNDER_PYTEST", "1")
    crash_report._installed_for = None
    before = sys.excepthook
    try:
        crash_report.install("jeeves", flush=False)
        assert crash_report._installed_for == "jeeves"
        assert sys.excepthook is not before
    finally:
        sys.excepthook = before
        crash_report._installed_for = None


def test_mrb2538_shipped_set_covers_ear_and_worker():
    names = {n.lower() for n in crash_report._SHIPPED_EXE_INSTALL}
    for n in ("jeeves", "bob-ear", "bob-worker", "airc"):
        assert n in names


def test_mrb2538_source_gates():
    from pathlib import Path

    src = Path(crash_report.__file__).read_text(encoding="utf-8")
    assert "FR #2535" in src
    assert "PYTEST_CURRENT_TEST" in src
    assert "BOB_CRASH_ALLOW_UNDER_PYTEST" in src
    assert "_is_pytest_untrusted_mount" in src
