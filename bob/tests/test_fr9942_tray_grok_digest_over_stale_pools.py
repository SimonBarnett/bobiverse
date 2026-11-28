"""FR #9942: live digest xai_weekly 0% must beat stale tray-digest-pools Grok %."""
from __future__ import annotations

import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
START = ROOT / "tray" / "tools" / "BobTrayStartWorker.ps1"
PS = shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS, reason="needs PowerShell")


def test_fr9942_grok_fuel_reader_prefers_digest_xai_weekly():
    text = WATCH.read_text(encoding="utf-8-sig")
    fn = text.split("function Get-BobTrayGrokFuelRemaining", 1)[1].split("function ", 1)[0]
    assert "FR #9942" in fn
    assert "Get-BobTrayMachineXaiWeekly" in fn
    assert "tray-digest-pools" in fn or "TipForm" in fn


def test_fr9942_under_cap_uses_empty_online_fill_choice():
    text = WATCH.read_text(encoding="utf-8-sig")
    uc = text.split("Get-BobTrayUnderCapFillCount", 1)[1].split("# FR #8890", 1)[0]
    assert "under-cap skip" in uc
    assert "Get-BobTrayEmptyOnlineFillAgentChoice" in uc


@needs_ps
def test_fr9942_digest_zero_beats_stale_snapshot(tmp_path: Path):
    watch_fn = WATCH.read_text(encoding="utf-8-sig")
    m = re.search(r"(?ms)^function Get-BobTrayGrokFuelRemaining\b.*?\n\}", watch_fn)
    assert m, "Get-BobTrayGrokFuelRemaining missing"
    body = m.group(0)
    script = tmp_path / "t.ps1"
    script.write_text(
        textwrap.dedent(
            f"""
            $ErrorActionPreference = 'Stop'
            function Resolve-BobiverseMachineId {{ param($Id) return ([string]$Id).ToLowerInvariant() }}
            function Get-BobTrayFuelLocalMachineId {{ return 'flamingo' }}
            function Get-BobTrayMachineXaiWeekly {{
                return [pscustomobject]@{{
                    remaining_pct = 0
                    fresh         = $true
                    age_s         = 5
                }}
            }}
            $script:lastFuelSnapshot = [pscustomobject]@{{
                machines = @([pscustomobject]@{{
                    id = 'flamingo'
                    remaining_pct = 94
                }})
            }}
            {body}
            $r = Get-BobTrayGrokFuelRemaining
            Write-Output $r
            """
        ),
        encoding="utf-8-sig",
    )
    out = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert out.returncode == 0, out.stderr
    assert "0" in (out.stdout or "")


@needs_ps
def test_fr9942_empty_online_choice_pins_opencode_when_grok_zero(tmp_path: Path):
    start = START.read_text(encoding="utf-8-sig")
    script = tmp_path / "t2.ps1"
    script.write_text(
        textwrap.dedent(
            f"""
            $ErrorActionPreference = 'Stop'
            function Resolve-BobTrayOpencodeSlotModel {{ return 'glm-5' }}
            . '{START.as_posix()}'
            $c = Get-BobTrayEmptyOnlineFillAgentChoice -GrokRemaining 0 -OpencodeFreeRemaining 33 -Root '{tmp_path.as_posix()}'
            Write-Output ("{{0}}|{{1}}|{{2}}" -f $(if ($c.skip) {{'skip'}} else {{'ok'}}), $c.agent, $c.slot)
            """
        ),
        encoding="utf-8-sig",
    )
    out = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert out.returncode == 0, out.stderr
    assert "ok|opencode|free" in out.stdout.replace("\r", "")