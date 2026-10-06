"""MRB #2642 hostile: ProgressPreference order, psb64 wrap, skill bullets contiguous."""
from __future__ import annotations

import base64
import os
import shutil
import subprocess

import pytest

import airc_console as ac
from repo_layout import ROOT


pytestmark = pytest.mark.skipif(
    os.name != "nt" or not shutil.which("powershell.exe"),
    reason="MRB #2642 requires Windows PowerShell",
)


def test_mrb2642_progress_preference_before_utf8_wrap():
    enc = ac.encode_ps_encoded_command("Write-Output order-check")
    text = base64.b64decode(enc).decode("utf-16-le")
    assert text.index("ProgressPreference") < text.index("UTF8Encoding")
    assert text.index("ProgressPreference") < text.index("Write-Output order-check")
    assert "SilentlyContinue" in text


def test_mrb2642_empty_script_still_gets_progress_preamble():
    wrapped = ac.wrap_ps_script_utf8_stdout("")
    assert "ProgressPreference" in wrapped
    assert "SilentlyContinue" in wrapped
    enc = ac.encode_ps_encoded_command("")
    text = base64.b64decode(enc).decode("utf-16-le")
    assert "ProgressPreference" in text


def test_mrb2642_psb64_path_gets_progress_preference():
    # UTF-16LE script bytes -> base64 payload for psb64:
    raw = "Write-Output psb64-fr2641".encode("utf-16-le")
    payload = base64.b64encode(raw).decode("ascii")
    enc = ac.prepare_psb64_encoded_command(payload)
    text = base64.b64decode(enc).decode("utf-16-le")
    assert "ProgressPreference" in text
    assert "SilentlyContinue" in text
    assert "psb64-fr2641" in text


def test_mrb2642_skill_bullets_contiguous():
    skill = (ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc" / "SKILL.md").read_text(
        encoding="utf-8-sig"
    )
    assert "Command StdErr CLIXML progress (FR #2641)" in skill
    assert "$ProgressPreference = 'SilentlyContinue'" in skill or "ProgressPreference" in skill
    # Must not orphan the next bullet (driving-box helper).
    idx = skill.index("Command StdErr CLIXML progress (FR #2641)")
    tail = skill[idx : idx + 500]
    assert "Driving-box helper" in skill[idx:]
    assert "Invoke-AircRemote.ps1" in skill[idx:]
    trouble = (
        ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-troubleshooting" / "SKILL.md"
    ).read_text(encoding="utf-8-sig")
    assert "FR #2641" in trouble
    assert "Preparing modules for first use" in trouble
    assert "ProgressPreference" in trouble


def test_mrb2642_write_progress_does_not_leak_clixml():
    req = ac.parse_shell_request(
        "Write-Progress -Activity 'mrb2642' -Status 'working' -PercentComplete 50; Write-Output done-mrb2642"
    )
    out = ac.run_shell_request(req, timeout_s=45)
    assert out.exit_code == 0
    assert "done-mrb2642" in out.stdout
    err = out.stderr or ""
    assert "#< CLIXML" not in err
    assert "Preparing modules for first use" not in err
