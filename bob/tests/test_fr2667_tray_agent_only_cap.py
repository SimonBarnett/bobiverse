"""FR #2667: tray cap is agent-only (align with FR #2522 / startworker / bob_worker).

Plan/maintenance must start on top of 2 agent seats; Measure counts agent roots only;
CapRefusal(-Mode plan) is empty; startworker res reason is ``cap`` (not launch-failed).
"""
from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRAY_TOOLS = ROOT / "bob" / "tray" / "tools"
START_PS1 = TRAY_TOOLS / "BobTrayStartWorker.ps1"
WATCH_PS1 = TRAY_TOOLS / "Watch-BobTray.ps1"
TRAY_CS = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
BUILD_PS1 = ROOT / "bob" / "scripts" / "Build-BobDialogs.ps1"


def _ps(script: str) -> str:
    r = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    return out


def test_fr2667_measure_counts_agent_only_ignores_plan_maintenance():
    """Fails on tip: Measure counts every bob-worker root."""
    script = textwrap.dedent(
        f"""
        . '{START_PS1}'
        function P($id,$pp,$name,$cl) {{
          [pscustomobject]@{{ ProcessId=$id; ParentProcessId=$pp; Name=$name; CommandLine=$cl }}
        }}
        $twoAgent = @(
          (P 10 1 'bob-worker.exe' 'bob-worker.exe --mode agent'),
          (P 11 10 'bob-worker.exe' 'bob-worker.exe --mode agent'),
          (P 20 1 'bob-worker.exe' 'bob-worker.exe --mode agent'),
          (P 21 20 'bob-worker.exe' 'bob-worker.exe --mode agent')
        )
        $mixed = $twoAgent + @(
          (P 30 1 'bob-worker.exe' 'bob-worker.exe --mode plan'),
          (P 31 30 'bob-worker.exe' 'bob-worker.exe --mode plan'),
          (P 40 1 'bob-worker.exe' 'bob-worker.exe --mode maintenance'),
          (P 41 40 'bob-worker.exe' 'bob-worker.exe --mode maintenance')
        )
        "AGENT=" + (Measure-BobTrayWorkerSeats -Procs $mixed)
        "ALL=" + (Measure-BobTrayWorkerSeats -Procs $mixed -Modes @('agent','plan','maintenance','monitor'))
        "PLAN_REF=[" + (Get-BobTrayWorkerCapRefusal -Procs $mixed -Mode plan) + "]"
        "MAINT_REF=[" + (Get-BobTrayWorkerCapRefusal -Procs $mixed -Mode maintenance) + "]"
        "AGENT_REF=[" + (Get-BobTrayWorkerCapRefusal -Procs $mixed -Mode agent) + "]"
        "ONE_AGENT_PLAN=[" + (Get-BobTrayWorkerCapRefusal -Procs $twoAgent -Mode plan) + "]"
        """
    )
    out = _ps(script)
    assert "AGENT=2" in out, out
    assert "ALL=4" in out, out
    assert "PLAN_REF=[]" in out, out
    assert "MAINT_REF=[]" in out, out
    assert "ONE_AGENT_PLAN=[]" in out, out
    assert "AGENT_REF=[Max 2 workers (2 already running)" in out, out


def test_fr2667_startworker_queue_writes_reason_cap():
    """When Launch returns 0 because of cap, res reason must be cap (not launch-failed)."""
    src = START_PS1.read_text(encoding="utf-8")
    # Queue consumer must set reason=cap when CapRefusal fires for the requested mode.
    assert "reason = 'cap'" in src or 'reason = "cap"' in src
    assert "Get-BobTrayWorkerCapRefusal" in src
    watch = WATCH_PS1.read_text(encoding="utf-8")
    i = watch.index("function Start-BobTrayWorkerExe")
    body = watch[i : i + 2500]
    assert "Get-BobTrayWorkerCapRefusal -Mode" in body or "Get-BobTrayWorkerCapRefusal -Mode $Mode" in body


def test_fr2667_csharp_cap_refusal_mode_aware():
    cs = TRAY_CS.read_text(encoding="utf-8")
    assert "CapRefusal(string mode" in cs or "CapRefusal(string mode =" in cs
    assert 'mode, "agent"' in cs or 'Equals(mode, "agent"' in cs or 'mode == "agent"' in cs.lower() or 'OrdinalIgnoreCase' in cs
    # Launch must pass mode into CapRefusal
    assert "CapRefusal(mode)" in cs
    # Agent-only seat count (CommandLine / --mode)
    assert "--mode" in cs
    build = BUILD_PS1.read_text(encoding="utf-8")
    # System.Management needed for Win32_Process.CommandLine (or documented equivalent).
    assert "System.Management" in cs or "System.Management.dll" in build or "CommandLine" in cs


def test_fr2667_comments_no_longer_say_agent_or_plan_cap():
    ps1 = START_PS1.read_text(encoding="utf-8")
    assert "agent or plan" not in ps1.lower() or "ONLY mode=agent" in ps1 or "agent-only" in ps1.lower() or "FR #2667" in ps1
    assert "FR #2667" in ps1 or "FR #2522" in ps1
