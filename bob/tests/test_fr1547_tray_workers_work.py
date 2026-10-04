"""FR #1547: Get-BobTrayWorkersFromNickMap must read Jeeves workers[].work (TipForm activity)."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from repo_layout import ROOT

TRAY = ROOT / "third_party" / "bob-tray"
HOVER = TRAY / "src" / "Public" / "Get-BobTrayHover.ps1"
PS = shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def _run(body: str, tmp_path: Path) -> list[str]:
    script = tmp_path / "t.ps1"
    script.write_bytes(
        (
            "\ufeff$ErrorActionPreference='Stop'\r\n"
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\r\n"
            f"Import-Module '{TRAY / 'src' / 'BobBridge.psd1'}' -Force -DisableNameChecking\r\n"
            "& (Get-Module BobBridge) {\r\n" + body + "\r\n}\r\n"
        ).encode("utf-8")
    )
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    return r.stdout.decode("utf-8", "replace").splitlines()


def test_hover_nickmap_reads_work_field_static():
    src = _txt(HOVER)
    i = src.index("function Get-BobTrayWorkersFromNickMap")
    end = src.find("\nfunction ", i + 1)
    body = src[i : end if end > i else i + 4000]
    # Exact property reads (avoid matching $val.working_on).
    assert "elseif ($val.work)" in body
    assert "elseif ($wn.work)" in body
    assert "working_on" in body


@needs_ps
def test_nickmap_work_fills_job_when_job_absent(tmp_path):
    out = _run(
        """
$node = [pscustomobject]@{
  'marchhare-41928' = [pscustomobject]@{ state = 'doing'; work = 'FR bobiverse#1547 tray work' }
}
$seats = @(Get-BobTrayWorkersFromNickMap -WorkersNode $node -MachineIdFilter 'marchhare')
'{0}|{1}|{2}' -f $seats.Count, $seats[0].nick, $seats[0].job
""",
        tmp_path,
    )
    assert out[-1] == "1|marchhare-41928|FR bobiverse#1547 tray work"


@needs_ps
def test_nickmap_job_still_wins_over_work(tmp_path):
    out = _run(
        """
$node = [pscustomobject]@{
  'marchhare-1' = [pscustomobject]@{ state = 'doing'; job = 'from-job'; work = 'from-work' }
}
$seats = @(Get-BobTrayWorkersFromNickMap -WorkersNode $node -MachineIdFilter 'marchhare')
$seats[0].job
""",
        tmp_path,
    )
    assert out[-1] == "from-job"


@needs_ps
def test_array_workers_work_field(tmp_path):
    out = _run(
        """
$arr = @(
  [pscustomobject]@{ nick = 'marchhare-2'; state = 'doing'; work = 'array-work-only' }
)
$seats = @(Get-BobTrayWorkersFromNickMap -WorkersNode $arr -MachineIdFilter 'marchhare')
$seats[0].job
""",
        tmp_path,
    )
    assert out[-1] == "array-work-only"
