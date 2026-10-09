"""MRB #3760 hostile: FR #3759 Install-Airc PS 4.0 -File explicit exit."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

PS1 = ROOT / "airc" / "scripts" / "Install-Airc.ps1"
CMD = ROOT / "airc" / "scripts" / "Install-Airc.cmd"
SKILL = (
    ROOT
    / "airc"
    / ".grok"
    / "skills"
    / "bobiverse-airc-troubleshooting"
    / "SKILL.md"
)
PIN = ROOT / "airc" / "tests" / "test_fr3759_ps40_install_exit.py"


def test_mrb3760_hostile_ps1_exit_after_finally():
    text = PS1.read_text(encoding="utf-8")
    assert "FR #3759" in text
    assert "$script:AircExitCode" in text
    assert "exit [int]$script:AircExitCode" in text
    # fail path must not bare-throw as the MSI signal
    assert "# FR #3759: do not bare-throw here" in text or "AircExitCode = 1" in text


def test_mrb3760_hostile_cmd_fail_flag_when_ec0():
    text = CMD.read_text(encoding="utf-8")
    assert "FR #3759" in text or "FR3759" in text
    assert "FAILFLAG" in text
    assert 'if "%EC%"=="0" if exist "%FAILFLAG%"' in text
    assert 'del /f /q "%FAILFLAG%"' in text


def test_mrb3760_hostile_ascii_skill_and_pin():
    for p in (PS1, CMD, PIN):
        raw = p.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), p.name
        assert all(b < 128 for b in raw), p.name
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3759" in skill
    assert "AircExitCode" in skill or "fail-reported.flag" in skill
    assert PIN.is_file()
