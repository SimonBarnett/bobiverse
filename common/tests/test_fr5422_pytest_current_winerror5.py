"""FR #5422: pytest sessionfinish WinError 5 on pytest-current is not a product fail."""
from __future__ import annotations

import crash_report


def _winerror(code: int, path: str) -> OSError:
    err = PermissionError(f"[WinError {code}] Access is denied: {path!r}")
    err.winerror = code
    err.errno = 13
    return err


def test_fr5422_should_skip_winerror5_pytest_current():
    exc = _winerror(5, r"C:\Users\simon\AppData\Local\Temp\pytest-of-simon\pytest-current")
    assert crash_report.should_skip_report("jeeves", exc)
    assert crash_report.should_skip_report(
        "bob-worker",
        None,
        body="PermissionError: [WinError 5] Access is denied: pytest-current",
    )


def test_fr5422_should_not_skip_unrelated_access_denied():
    exc = _winerror(5, r"C:\ProgramData\bobiverse\state.json")
    assert not crash_report.should_skip_report("jeeves", exc)


def test_fr5422_cleanup_dead_symlinks_swallows_winerror5():
    def boom(_root):
        raise _winerror(5, r"%TEMP%\pytest-of-simon\pytest-current")

    wrapped = crash_report.wrap_cleanup_dead_symlinks(boom)
    assert wrapped("root") is None

    def other(_root):
        raise OSError("disk full")

    wrapped_other = crash_report.wrap_cleanup_dead_symlinks(other)
    try:
        wrapped_other("root")
        raise AssertionError("unrelated OSError must propagate")
    except OSError as e:
        assert "disk full" in str(e)
