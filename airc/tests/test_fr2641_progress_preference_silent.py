"""FR #2641: PowerShell Command must not leak CLIXML progress into StdErr.

Redirected powershell.exe emits ``#< CLIXML`` progress records
(``Preparing modules for first use``) on stderr unless
``$ProgressPreference = 'SilentlyContinue'``. That costs IRC flood lines and
makes StdErr look non-empty to callers even when ExitCode is 0.
"""
from __future__ import annotations

import base64
import os
import shutil
import subprocess

import pytest

import airc_console as ac


pytestmark = pytest.mark.skipif(
    os.name != "nt" or not shutil.which("powershell.exe"),
    reason="FR #2641 requires Windows PowerShell",
)


def test_encode_ps_sets_progress_preference_silently_continue():
    enc = ac.encode_ps_encoded_command("Write-Output hi")
    text = base64.b64decode(enc).decode("utf-16-le")
    assert "ProgressPreference" in text
    assert "SilentlyContinue" in text
    assert "Write-Output hi" in text
    # FR #2580 wrap must remain.
    assert "UTF8Encoding" in text
    assert "$OutputEncoding" in text


def test_wrap_ps_script_includes_progress_preference():
    wrapped = ac.wrap_ps_script_utf8_stdout("Write-Error boom")
    assert "ProgressPreference" in wrapped
    assert wrapped.index("ProgressPreference") < wrapped.index("Write-Error boom")


def test_plain_write_output_stderr_has_no_clixml_progress():
    req = ac.parse_shell_request("Write-Output hi-fr2641")
    out = ac.run_shell_request(req, timeout_s=45)
    assert out.exit_code == 0
    assert "hi-fr2641" in out.stdout
    err = out.stderr or ""
    assert "#< CLIXML" not in err
    assert "Preparing modules for first use" not in err
    assert "<Obj S=\"progress\"" not in err
    assert "progress" not in err.lower() or "Preparing modules" not in err


def test_write_error_still_reaches_stderr():
    req = ac.parse_shell_request("Write-Error 'fr2641-real-err'; exit 1")
    out = ac.run_shell_request(req, timeout_s=45)
    assert out.exit_code != 0
    err = out.stderr or ""
    assert "fr2641-real-err" in err
    # Progress noise must stay gone; Write-Error may still use CLIXML Error records.
    assert "Preparing modules for first use" not in err


def test_encoded_command_subprocess_stderr_clean():
    """Direct -EncodedCommand capture (same path airc uses)."""
    enc = ac.encode_ps_encoded_command("Write-Output ok2641")
    ps = ac.resolve_powershell()
    proc = subprocess.run(
        [ps, "-NoProfile", "-NonInteractive", "-EncodedCommand", enc],
        capture_output=True,
        timeout=45,
        check=False,
    )
    assert proc.returncode == 0
    stderr = proc.stderr.decode("utf-8", errors="replace")
    assert "#< CLIXML" not in stderr
    assert "Preparing modules for first use" not in stderr
