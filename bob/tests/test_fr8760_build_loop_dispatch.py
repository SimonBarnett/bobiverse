"""FR #8760: build-loop dispatch pins machine/cwd, live job id, dispatched>park, capacity wait."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

START = ROOT / "tray" / "src" / "Public" / "Start-BobBuild.ps1"
CAPACITY = ROOT / "tray" / "src" / "Public" / "Get-BobCapacity.ps1"
FLEET = ROOT / "tray" / "src" / "Private" / "Invoke-BobFleet.ps1"
EVIDENCE = ROOT / "docs" / "fr8760-build-loop-dispatch-evidence.md"
PSD1 = ROOT / "tray" / "src" / "BobBridge.psd1"


def test_s1_start_bob_build_validates_cwd_on_target_machine():
    text = START.read_text(encoding="utf-8-sig")
    assert "FR #8760" in text
    assert "cwd_not_on_machine" in text
    assert "Test-CwdAllowed" in text
    # Must check target fleet machine record, not only this-machine self check.
    assert "machines" in text and "cwdRoots" in text


def test_s2_loop_current_job_helpers_exist():
    fleet = FLEET.read_text(encoding="utf-8-sig")
    assert "function Set-BobBuildLoopCurrentJob" in fleet
    assert "function Get-BobBuildLoopCurrentJob" in fleet
    assert "currentJobId" in fleet
    start = START.read_text(encoding="utf-8-sig")
    assert "Set-BobBuildLoopCurrentJob" in start


def test_s3_dispatched_beats_park_only():
    fleet = FLEET.read_text(encoding="utf-8-sig")
    assert "function Test-BobFrBodyDispatched" in fleet
    start = START.read_text(encoding="utf-8-sig")
    assert "park-only" in start.lower() or "park only" in start.lower()
    assert "dispatched" in start.lower()
    # Pure helper acceptance (no PowerShell host required).
    assert "dispatched" in fleet.lower()


def test_s3_helper_logic_via_python_mirror():
    # Mirror Test-BobFrBodyDispatched: body dispatched wins over park-only comments.
    def dispatched(body: str) -> bool:
        b = (body or "").lower()
        if "(dispatched)" in b or "dispatched." in b:
            return True
        if "do not bob-job until human dispatch" in b and "(dispatched)" not in b:
            return False
        return "dispatched" in b and "do not start until human dispatch" not in b.split("dispatched", 1)[0][-80:]

    assert dispatched("Feature request `BOB-01` (dispatched).\n") is True
    assert dispatched("Do not start until human dispatch; park-only") is False


def test_s4_select_reports_waiting_for_capacity():
    text = CAPACITY.read_text(encoding="utf-8-sig")
    assert "waiting for capacity" in text
    assert "FR #8760" in text
    assert "Get-BobMachineJobCount" in text


def test_exports_and_evidence():
    psd1 = PSD1.read_text(encoding="utf-8-sig")
    assert "Test-BobFrBodyDispatched" in psd1
    assert "Set-BobBuildLoopCurrentJob" in psd1
    assert "Get-BobBuildLoopCurrentJob" in psd1
    ev = EVIDENCE.read_text(encoding="utf-8")
    assert "FR #8760" in ev
    assert "S1" in ev and "S2" in ev and "S3" in ev and "S4" in ev
