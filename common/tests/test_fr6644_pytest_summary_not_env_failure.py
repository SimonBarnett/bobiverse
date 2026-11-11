"""FR #6644: pytest summary + FileNotFoundError traceback is a test failure, not env."""
from __future__ import annotations

import bobiverse_build as bb


_PYTEST_SUMMARY_WITH_FNF = """
============================= test session starts =============================
collected 2630 items

common/tests/test_fr3717_pre_rmdir_removes_cdkout_before_git.py F        [  0%]
...
================================== FAILURES ===================================
________________ test_fr3717_pre_rmdir_removes_cdkout_before_git _______________
E   FileNotFoundError: [WinError 3] The system cannot find the path specified:
    'D:\\\\...\\\\cdk.out\\\\...\\\\python'
=========================== short test summary info ===========================
FAILED common/tests/test_fr3717_pre_rmdir_removes_cdkout_before_git.py::test_fr3717_pre_rmdir_removes_cdkout_before_git
================== 6 failed, 2624 passed in 120.00s ==================
"""


def test_fr6644_summary_plus_filenotfound_is_not_env_failure():
    assert bb.has_pytest_session_or_summary(_PYTEST_SUMMARY_WITH_FNF) is True
    assert bb.is_command_not_found(_PYTEST_SUMMARY_WITH_FNF, 1) is False


def test_fr6644_exit_9009_without_summary_is_env_failure():
    msg = (
        "'python' is not recognized as an internal or external command,\n"
        "operable program or batch file.\n"
    )
    assert bb.has_pytest_session_or_summary(msg) is False
    assert bb.is_command_not_found(msg, 9009) is True


def test_fr6644_missing_interpreter_before_pytest_is_env_failure():
    msg = (
        "Traceback (most recent call last):\n"
        "  File \"C:\\\\Windows\\\\py.exe\", line 1, in <module>\n"
        "FileNotFoundError: [Errno 2] No such file or directory: 'python'\n"
    )
    assert bb.has_pytest_session_or_summary(msg) is False
    assert bb.is_command_not_found(msg, 1) is True


def test_fr6644_plain_assertion_failure_still_not_env():
    out = "FAILED tests/test_x.py::t - assert 0\n===== 1 failed in 0.10s =====\n"
    assert bb.is_command_not_found(out, 1) is False
