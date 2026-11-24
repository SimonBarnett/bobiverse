"""FR #9078: ConsoleLauncher retries CreateProcess without BREAKAWAY on Access Denied (5)."""
from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from repo_layout import ROOT

WATCH = ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
DOCS = ROOT / "bob" / "docs" / "bob-worker.md"
PS = shutil.which("powershell") or shutil.which("pwsh")
WIN = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr9078_source_pins_fallback_and_docs():
    w = _txt(WATCH)
    assert "ERROR_ACCESS_DENIED" in w
    assert "FR #9078" in w
    assert "CREATE_NEW_CONSOLE | CREATE_UNICODE_ENVIRONMENT | CREATE_BREAKAWAY_FROM_JOB" in w
    assert "CREATE_NEW_CONSOLE | CREATE_UNICODE_ENVIRONMENT, block" in w
    d = _txt(DOCS)
    assert "FR #9078" in d
    assert "Access Denied" in d or "Access Denied (5)" in d
    assert "Reload engine" in d or "reload the engine" in d.lower()
    assert "WorkerLauncher.Launch" in d


@WIN
def test_fr9078_launch_succeeds_under_job_without_breakaway_ok(tmp_path: Path):
    """Under a job that forbids breakaway, Start must still return pid>0 (fallback path)."""
    helper = tmp_path / "fr9078_job.ps1"
    whoami = Path(r"C:\Windows\System32\whoami.exe")
    standin = tmp_path / "whoami-standin.exe"
    shutil.copy(whoami, standin)
    watch_ps = str(WATCH).replace("'", "''")
    standin_ps = str(standin).replace("'", "''")
    helper.write_text(
        textwrap.dedent(
            f"""
            $ErrorActionPreference = 'Stop'
            Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class JobShim {{
  [StructLayout(LayoutKind.Sequential)]
  public struct JOBOBJECT_BASIC_LIMIT_INFORMATION {{
    public long PerProcessUserTimeLimit; public long PerJobUserTimeLimit;
    public uint LimitFlags; public UIntPtr MinimumWorkingSetSize; public UIntPtr MaximumWorkingSetSize;
    public uint ActiveProcessLimit; public UIntPtr Affinity; public uint PriorityClass; public uint SchedulingClass;
  }}
  [StructLayout(LayoutKind.Sequential)]
  public struct IO_COUNTERS {{
    public ulong a,b,c,d,e,f;
  }}
  [StructLayout(LayoutKind.Sequential)]
  public struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION {{
    public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation;
    public IO_COUNTERS IoInfo;
    public UIntPtr ProcessMemoryLimit; public UIntPtr JobMemoryLimit;
    public UIntPtr PeakProcessMemoryUsed; public UIntPtr PeakJobMemoryUsed;
  }}
  [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
  public static extern IntPtr CreateJobObjectW(IntPtr a, string name);
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern bool SetInformationJobObject(IntPtr job, int infoClass, ref JOBOBJECT_EXTENDED_LIMIT_INFORMATION info, int len);
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern bool IsProcessInJob(IntPtr process, IntPtr job, out bool result);
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern bool CloseHandle(IntPtr h);
  [DllImport("kernel32.dll")]
  public static extern IntPtr GetCurrentProcess();
  public const uint JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000;
  public const int JobObjectExtendedLimitInformation = 9;
}}
'@
            $job = [JobShim]::CreateJobObjectW([IntPtr]::Zero, $null)
            if ($job -eq [IntPtr]::Zero) {{ Write-Output 'SKIP create-job-failed'; exit 0 }}
            try {{
                $info = New-Object JobShim+JOBOBJECT_EXTENDED_LIMIT_INFORMATION
                $info.BasicLimitInformation.LimitFlags = [JobShim]::JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                if (-not [JobShim]::SetInformationJobObject($job, [JobShim]::JobObjectExtendedLimitInformation, [ref]$info, [Runtime.InteropServices.Marshal]::SizeOf($info))) {{
                    Write-Output 'SKIP set-job-info-failed'; exit 0
                }}
                if (-not [JobShim]::AssignProcessToJobObject($job, [JobShim]::GetCurrentProcess())) {{
                    Write-Output ('SKIP assign-failed err=' + [Runtime.InteropServices.Marshal]::GetLastWin32Error())
                    exit 0
                }}
                $ast = [System.Management.Automation.Language.Parser]::ParseFile('{watch_ps}', [ref]$null, [ref]$null)
                $fn = $ast.Find({{ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Initialize-BobTrayConsoleLauncher' }}, $true).Extent.Text
                Invoke-Expression $fn
                Initialize-BobTrayConsoleLauncher
                $pidChild = [BobTray.ConsoleLauncher]::Start('{standin_ps}', ('"' + '{standin_ps}' + '"'), '{str(tmp_path).replace(chr(39), chr(39)+chr(39))}', 'fr9078', $null)
                if ($pidChild -le 0) {{ throw 'pid<=0' }}
                $proc = Get-Process -Id $pidChild -ErrorAction SilentlyContinue
                $inJob = $false
                if ($proc) {{
                    $h = $proc.Handle
                    [void][JobShim]::IsProcessInJob($h, $job, [ref]$inJob)
                    try {{ Stop-Process -Id $pidChild -Force -ErrorAction SilentlyContinue }} catch {{ }}
                }}
                if (-not $inJob) {{ throw 'child not in job (breakaway unexpectedly succeeded or IsProcessInJob failed)' }}
                Write-Output ('ok pid=' + $pidChild)
            }}
            finally {{
                if ($job -ne [IntPtr]::Zero) {{ [void][JobShim]::CloseHandle($job) }}
            }}
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(helper)],
        capture_output=True,
        text=True,
        timeout=90,
    )
    out = (r.stdout or "") + "\n" + (r.stderr or "")
    if "SKIP " in out:
        pytest.skip(out.strip().splitlines()[-1])
    assert r.returncode == 0, out
    assert "ok pid=" in out, out
