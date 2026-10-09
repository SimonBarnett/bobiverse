"""FR #3773: trailing backslash in ``cmd:`` must not break cmd.exe /c.

``subprocess`` list argv uses ``list2cmdline``, which doubles a trailing ``\\``
before the closing quote (CreateProcess rules). cmd.exe ``/c`` then sees
``dir C:\\\\`` and fails with 'The filename ... syntax is incorrect'.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

import airc_console as ac


pytestmark = pytest.mark.skipif(
    os.name != "nt" or not shutil.which("cmd.exe"),
    reason="FR #3773 requires Windows cmd.exe",
)


def test_fr3773_list2cmdline_doubles_trailing_backslash_repro():
    """Pin the Windows bug class: list argv mangles ``dir C:\\``."""
    body = "dir C:" + "\\"
    cl = subprocess.list2cmdline(["cmd.exe", "/d", "/c", body])
    # Doubled backslash before closing quote — the broken form.
    assert cl.endswith('"')
    assert 'C:\\\\"' in cl.replace("/", "\\") or cl.rstrip().endswith('\\\\"')


def test_fr3773_build_cmd_command_line_preserves_single_trailing_backslash():
    body = "dir C:" + "\\"
    cl = ac.build_cmd_command_line(body)
    assert "/s" in cl.lower().split()
    assert "/c" in cl.lower().split()
    # Must NOT double the path backslash before the closing quote.
    assert "C:\\\\\"" not in cl
    assert "C:\\\"'" not in cl
    # Ends with ...C:\ "  (single backslash then close quote)
    assert cl.rstrip().endswith('C:\\"') or 'C:\\"' in cl


def test_fr3773_run_cmd_dir_drive_root_trailing_backslash():
    req = ac.parse_shell_request("cmd: dir C:" + "\\")
    assert req.kind == "cmd"
    out = ac.run_shell_request(req, timeout_s=30)
    assert out.exit_code == 0, (out.stdout, out.stderr)
    assert "Directory of" in out.stdout
    # Root of C:, not the process cwd.
    assert re_dir_of_root(out.stdout)


def test_fr3773_run_cmd_program_files_trailing_backslash():
    req = ac.parse_shell_request('cmd: dir "C:\\Program Files\\"')
    out = ac.run_shell_request(req, timeout_s=30)
    assert out.exit_code == 0, (out.stdout, out.stderr)
    assert "Directory of" in out.stdout
    assert "Program Files" in out.stdout


def test_fr3773_run_cmd_without_trailing_backslash_still_works():
    req = ac.parse_shell_request("cmd: dir C:")
    out = ac.run_shell_request(req, timeout_s=30)
    assert out.exit_code == 0, (out.stdout, out.stderr)
    assert "Directory of" in out.stdout


def test_fr3773_build_shell_argv_includes_s_for_cmd(monkeypatch):
    monkeypatch.setenv("COMSPEC", r"C:\Windows\System32\cmd.exe")
    req = ac.parse_shell_request("cmd: echo %COMSPEC%")
    argv = ac.build_shell_argv(req)
    assert argv[0].lower().endswith("cmd.exe")
    low = [a.lower() for a in argv]
    assert "/s" in low
    assert "/c" in low


def re_dir_of_root(stdout: str) -> bool:
    for ln in stdout.splitlines():
        s = ln.strip()
        if not s.lower().startswith("directory of"):
            continue
        # ``Directory of C:\`` (optional trailing slash / space)
        tail = s.split(" ", 2)[-1].rstrip().rstrip("\\").upper()
        if tail == "C:":
            return True
    return False
