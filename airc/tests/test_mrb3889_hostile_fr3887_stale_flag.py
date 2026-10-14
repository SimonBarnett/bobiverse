"""MRB #3889 hostile pins for FR #3887 stale install-airc-fail-reported.flag."""
from __future__ import annotations

from repo_layout import ROOT

CMD = ROOT / "airc/scripts/Install-Airc.cmd"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md"
PIN = ROOT / "airc/tests/test_fr3887_stale_fail_flag.py"


def test_mrb3889_cmd_clears_stale_flag_before_ps1_invoke():
    text = CMD.read_text(encoding="utf-8")
    assert "FR #3887" in text
    needle = "FR3887 clearing stale fail-flag before install"
    assert needle in text
    clear_at = text.lower().find("fr3887 clearing stale")
    invoke_at = text.find(
        'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%HERE%Install-Airc.ps1"'
    )
    assert 0 <= clear_at < invoke_at
    # FR #3759 same-run belt must remain after the clear.
    assert 'if "%EC%"=="0" if exist "%FAILFLAG%"' in text
    assert text.find(needle) < text.find('if "%EC%"=="0" if exist "%FAILFLAG%"')


def test_mrb3889_troubleshooting_skill_row_contiguous():
    text = SKILL.read_text(encoding="utf-8")
    assert "FR #3887" in text
    assert "clears any leftover flag before invoking Install-Airc.ps1" in text
    assert "same-run flag writes still FAIL" in text
    assert not text.startswith("\ufeff")
    assert PIN.is_file()
