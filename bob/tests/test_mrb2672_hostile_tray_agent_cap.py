"""MRB #2672 hostile: tray hard cap is agent-only (FR #2667 / #2522).

Locks monitor uncapped, missing --mode defaults to agent for counting,
Ensure-BobWorkerSeats agent Modes, C# CapRefusal early-exit, Watch-BobTray -Mode.
"""
from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

from repo_layout import ROOT, resolve

START_PS1 = resolve("third_party/bob-tray/tools/BobTrayStartWorker.ps1")
WATCH_PS1 = resolve("third_party/bob-tray/tools/Watch-BobTray.ps1")
ENSURE = ROOT / "bob" / "scripts" / "Ensure-BobWorkerSeats.ps1"
TRAY_CS = resolve("third_party/bob-tray/dialogs/BobTray.cs")
VISION = ROOT / "bob" / "VISION.md"


def _ps(script: str) -> str:
    r = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    return out


def test_mrb2672_vision_one_window_worker_still_stated():
    text = VISION.read_text(encoding="utf-8")
    assert "One-window worker" in text or "one window" in text.lower()
    assert "bob-worker" in text.lower()


def test_mrb2672_monitor_and_missing_mode_defaults():
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
        $withMonitor = $twoAgent + @(
          (P 50 1 'bob-worker.exe' 'bob-worker.exe --mode monitor'),
          (P 51 50 'bob-worker.exe' 'bob-worker.exe --mode monitor')
        )
        $legacyNoMode = @(
          (P 60 1 'bob-worker.exe' 'C:\\ai\\bob\\worker\\bob-worker.exe'),
          (P 61 60 'bob-worker.exe' 'C:\\ai\\bob\\worker\\bob-worker.exe'),
          (P 70 1 'bob-worker.exe' 'C:\\ai\\bob\\worker\\bob-worker.exe'),
          (P 71 70 'bob-worker.exe' 'C:\\ai\\bob\\worker\\bob-worker.exe')
        )
        "MON_REF=[" + (Get-BobTrayWorkerCapRefusal -Procs $withMonitor -Mode monitor) + "]"
        "PLAN_ON_FULL=[" + (Get-BobTrayWorkerCapRefusal -Procs $withMonitor -Mode plan) + "]"
        "MODE_DEF=" + (Get-BobTrayWorkerSeatMode (P 1 0 'bob-worker.exe' 'bob-worker.exe'))
        "LEGACY_N=" + (Measure-BobTrayWorkerSeats -Procs $legacyNoMode)
        "LEGACY_REF=[" + (Get-BobTrayWorkerCapRefusal -Procs $legacyNoMode -Mode agent) + "]"
        """
    )
    out = _ps(script)
    assert "MON_REF=[]" in out, out
    assert "PLAN_ON_FULL=[]" in out, out
    assert "MODE_DEF=agent" in out, out
    assert "LEGACY_N=2" in out, out
    assert "LEGACY_REF=[Max 2 workers (2 already running)" in out, out


def test_mrb2672_ensure_and_watch_pass_mode():
    ensure = ENSURE.read_text(encoding="utf-8-sig")
    assert "Measure-BobTrayWorkerSeats" in ensure
    assert "-Modes @('agent')" in ensure or '-Modes @("agent")' in ensure
    # FR #3180: Ensure is report-only (no CapRefusal / no req queue); Watch still gates Launch.
    assert "report-only" in ensure.lower() or "FR #3180" in ensure
    watch = WATCH_PS1.read_text(encoding="utf-8-sig")
    i = watch.index("function Start-BobTrayWorkerExe")
    body = watch[i : i + 3000]
    assert "Get-BobTrayWorkerCapRefusal -Mode $Mode" in body


def test_mrb2672_csharp_caprefusal_skips_non_agent():
    cs = TRAY_CS.read_text(encoding="utf-8-sig")
    assert "public static string CapRefusal(string mode" in cs
    # Early return for non-agent before seat count
    i = cs.index("public static string CapRefusal(string mode")
    body = cs[i : i + 500]
    assert 'Equals(mode ?? "agent", "agent"' in body or 'StringComparison.OrdinalIgnoreCase' in body
    assert 'return ""' in body or "return string.Empty" in body
    assert "CapRefusal(mode)" in cs
    assert "SeatsForModes" in cs
