"""airc Command StdErr must be plain text, not PowerShell CLIXML (FR #2910 / follow-up to #2641)."""
from __future__ import annotations

import os
import shutil
import sys

import pytest

import airc_console as ac

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("powershell.exe"),
    reason="needs Windows PowerShell 5.1",
)


def _run(body: str) -> ac.ShellOutcome:
    return ac.run_shell_request(ac.ShellRequest(kind="ps", body=body), timeout_s=60)


def test_ps_error_stderr_is_plain_text_not_clixml():
    out = _run("Get-Item C:\\no_such_path_airc_stderr -ErrorAction Stop")
    assert out.exit_code != 0
    assert "#< CLIXML" not in out.stderr
    assert "<Objs" not in out.stderr
    assert "_x000D__x000A_" not in out.stderr
    assert "Cannot find path 'C:\\no_such_path_airc_stderr'" in out.stderr
    assert "ProgressPreference" not in out.stderr
    assert "OutputEncoding" not in out.stderr
    assert "UTF8Encoding" not in out.stderr
    # FR #2918: one-line user script reports At line:1 (not preamble+1).
    assert "At line:1 char:1" in out.stderr


def test_write_error_stderr_is_plain_text_not_clixml():
    out = _run("Write-Error 'boom-airc-2641b'; exit 4")
    assert out.exit_code == 4
    assert "#< CLIXML" not in out.stderr
    assert "<Objs" not in out.stderr
    assert "boom-airc-2641b" in out.stderr
    assert "ProgressPreference" not in out.stderr


def test_decode_clixml_stderr_unit():
    raw = (
        '#< CLIXML\r\n<Objs Version="1.1.0.1" xmlns="http://schemas.microsoft.com/powershell/2004/04">'
        '<S S="Error">Get-Item : Cannot find path \'C:\\x\' because it does not exist._x000D__x000A_</S>'
        '<S S="Error">At line:1 char:1_x000D__x000A_</S>'
        "</Objs>"
    )
    # Fixture is not preamble-wrapped — keep absolute At line:1.
    plain = ac.plain_text_powershell_stderr(raw, at_line_offset=0)
    assert "#< CLIXML" not in plain
    assert "<Objs" not in plain
    assert "_x000D_" not in plain
    assert "Cannot find path 'C:\\x'" in plain
    assert "At line:1 char:1" in plain


def test_adjust_at_line_subtracts_preamble_offset():
    raw = (
        '#< CLIXML\r\n<Objs Version="1.1.0.1" xmlns="http://schemas.microsoft.com/powershell/2004/04">'
        '<S S="Error">Get-Item : nope_x000D__x000A_</S>'
        '<S S="Error">At line:4 char:1_x000D__x000A_</S>'
        "</Objs>"
    )
    plain = ac.plain_text_powershell_stderr(raw)  # default = preamble line count
    assert ac.ps_utf8_preamble_line_count() == 3
    assert "At line:1 char:1" in plain
    assert "At line:4" not in plain


def test_multiline_script_error_reports_user_line_3():
    body = "Write-Output a\nWrite-Output b\nGet-Item C:\\no_such_path_airc_L3 -ErrorAction Stop"
    out = _run(body)
    assert out.exit_code != 0
    assert "Cannot find path 'C:\\no_such_path_airc_L3'" in out.stderr
    assert "At line:3 char:1" in out.stderr
    assert "At line:6" not in out.stderr


def test_preamble_is_on_own_lines():
    wrapped = ac.wrap_ps_script_utf8_stdout("Get-Item missing -ErrorAction Stop")
    assert "ProgressPreference" in wrapped
    # User script must not share the preamble statement line (char offsets).
    assert "\nGet-Item missing" in wrapped or wrapped.rstrip().endswith(
        "Get-Item missing -ErrorAction Stop"
    )
    pre_end = wrapped.index("Get-Item missing")
    assert "\n" in wrapped[:pre_end]
