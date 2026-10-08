"""MRB #3595 hostile pins for FR #3584 single install-fail intake."""
from __future__ import annotations

from repo_layout import ROOT

INSTALL = ROOT / "airc/scripts/Install-Airc.ps1"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"


def test_mrb3595_flag_set_before_send_and_outer_skips():
    t = INSTALL.read_text(encoding="utf-8-sig")
    assert "FR #3584" in t
    assert "$script:AircInstallFailReported = $false" in t
    # Nested catch sets flag before Send (even if Send throws).
    nest = t[t.find("ERROR Install-AircConsole") : t.find("Write-Host 'INFO Install-Airc done")]
    assert "$script:AircInstallFailReported = $true" in nest
    assert nest.find("$script:AircInstallFailReported = $true") < nest.find(
        "Send-BobiverseAircInstallFailureIntake"
    )
    assert "if (-not $script:AircInstallFailReported)" in t
    assert "skip outer install-fail intake" in t
    skill = SKILL.read_text(encoding="utf-8")
    assert "3584" in skill and "AircInstallFailReported" in skill
    assert "â" not in skill
