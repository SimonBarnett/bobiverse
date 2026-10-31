"""FR #5411: msiexec-exit intake must carry the exit code; 1603 is retried once."""
from __future__ import annotations

from repo_layout import ROOT

UPD = ROOT / "common/scripts/Update-BobiverseService.ps1"
COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md"


def test_fr5411_set_failure_forwards_detail():
    t = UPD.read_text(encoding="utf-8")
    fn = t[t.index("function Set-Failure") : t.index("function Write-CheckFailIntake")]
    assert "FR #5411" in fn
    assert "[string]$Detail" in fn
    assert "Send-BobiverseUpdateFailureIntake" in fn
    assert "-Detail $Detail" in fn or "-Detail $failMsg" in fn
    assert "Set-Failure -Tag $tag -Result $failResult -Detail $failMsg" in t


def test_fr5411_serialized_retries_1603():
    t = COMMON.read_text(encoding="utf-8")
    fn = t[t.index("function Invoke-BobiverseMsiexecSerialized") : t.index("function Get-BobiverseHeadlessPowerShellLaunch")]
    assert "FR #5411" in fn
    assert "$code -eq 1603" in fn
    i1618 = fn.index("$code -eq 1618")
    i1603 = fn.index("$code -eq 1603")
    assert i1603 > i1618


def test_fr5411_docs_name_msiexec_log():
    skill = SKILL.read_text(encoding="utf-8")
    assert "msiexec-exit" in skill
    assert "update\\<product>\\msiexec-" in skill or "msiexec-<tag>.log" in skill
    assert not SKILL.read_bytes().startswith(b"\xef\xbb\xbf")
    assert not UPD.read_bytes().startswith(b"\xef\xbb\xbf")
