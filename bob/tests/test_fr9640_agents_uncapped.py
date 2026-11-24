"""FR #9640: Agents Plan/Priority/Jeeves ignore Workers MaxWorkers=2 cap.

Workers submenu (--mode agent) stays capped at 2. Agents > Jeeves uses
--mode jeeves (IRC agent-like, uncapped). Plan/Priority stay on vendored
exes outside CapRefusal/Seats.
"""
from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

import bob_worker as bw
import worker_irc_seats as seats

ROOT = Path(__file__).resolve().parents[2]
TRAY_TOOLS = ROOT / "bob" / "tray" / "tools"
START_PS1 = TRAY_TOOLS / "BobTrayStartWorker.ps1"
WATCH_PS1 = TRAY_TOOLS / "Watch-BobTray.ps1"
TRAY_CS = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"


def _agent(*pids):
    out = []
    for p in pids:
        out.append((p, 1, "bob-worker.exe", "agent"))
        out.append((p + 1, p, "bob-worker.exe", "agent"))
    return out


def _alive_set(pids):
    live = {int(p) for p in pids}

    def fn(pid: int) -> bool:
        return int(pid) in live

    return fn


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


def test_fr9640_jeeves_mode_never_refused_by_worker_cap():
    procs = _agent(200, 300)
    assert bw.worker_cap_refusal(procs, 5000, for_mode="jeeves") == ""
    assert bw.worker_cap_refusal(procs, 5000, for_mode="agent") != ""
    assert "jeeves" in bw.UNCAPPED_MODES
    assert "jeeves" not in bw.CAPPED_MODES
    assert bw.is_irc_agent_like_mode("jeeves")
    assert bw.is_irc_agent_like_mode("agent")
    assert not bw.is_irc_agent_like_mode("plan")


def test_fr9640_jeeves_main_skips_cap_when_two_agents(monkeypatch, tmp_path):
    monkeypatch.setattr(bw, "snapshot_procs", lambda: _agent(200, 300))
    monkeypatch.setattr(bw, "_state_root", lambda: tmp_path)
    monkeypatch.setattr(bw, "ensure_console", lambda *a, **k: True)
    monkeypatch.setattr(bw.time, "sleep", lambda s: None)
    monkeypatch.setattr(bw, "count_irc_agent_seats", lambda **kw: 2)
    started = []
    monkeypatch.setattr(bw, "run_agent", lambda *a, **k: started.append("agent") or 0)
    assert bw.main(["--mode", "agent", "--install-root", str(tmp_path)]) == bw.EXIT_REFUSED
    assert bw.main(["--mode", "jeeves", "--install-root", str(tmp_path)]) == 0
    assert started == ["agent"]


def test_fr9640_jeeves_irc_marker_excluded_from_cap_count(tmp_path):
    seats.write_seat_irc(nick="w1", pid=11, machine="m", root=tmp_path, mode="agent")
    seats.write_seat_irc(nick="w2", pid=12, machine="m", root=tmp_path, mode="agent")
    seats.write_seat_irc(nick="jv", pid=99, machine="m", root=tmp_path, mode="jeeves")
    n = seats.count_irc_agent_seats(
        tmp_path, machine="m", pid_alive_fn=_alive_set([11, 12, 99])
    )
    assert n == 2
    body = json.loads((tmp_path / "jv.irc.json").read_text(encoding="utf-8"))
    assert body["mode"] == "jeeves"
    assert seats.worker_cap_refusal_irc(
        for_mode="jeeves",
        root=tmp_path,
        machine="m",
        pid_alive_fn=_alive_set([11, 12, 99]),
    ) == ""
    assert seats.worker_cap_refusal_irc(
        for_mode="agent",
        root=tmp_path,
        machine="m",
        pid_alive_fn=_alive_set([11, 12, 99]),
    ).startswith("max 2 workers")


def test_fr9640_describe_launch_accepts_jeeves(tmp_path):
    root = tmp_path / "bob"
    (root / "worker").mkdir(parents=True)
    local = tmp_path / "la"
    local.mkdir()
    plan = bw.describe_worker_exe_launch(
        str(root), "jeeves", local_app_data=str(local), source="tray"
    )
    assert plan["mode"] == "jeeves"
    assert "--mode" in plan["argv"] and "jeeves" in plan["argv"]
    assert "jeeves" in plan["title"].lower()


def test_fr9640_csharp_jeeves_start_and_modearg():
    cs = TRAY_CS.read_text(encoding="utf-8")
    assert 'StartWorker("jeeves"' in cs or "StartWorker(\"jeeves\"" in cs
    assert "jeeves" in cs
    assert r"(agent|plan|monitor|maintenance|jeeves)" in cs or "maintenance|jeeves" in cs
    assert "FR #9640" in cs
    # CapRefusal still agent-only
    assert 'Equals(mode ?? "agent", "agent"' in cs or 'Equals(mode, "agent"' in cs


def test_fr9640_ps_cap_refusal_jeeves_uncapped(tmp_path):
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
          (P 50 1 'bob-worker.exe' 'bob-worker.exe --mode jeeves'),
          (P 51 50 'bob-worker.exe' 'bob-worker.exe --mode jeeves')
        )
        $env:LOCALAPPDATA = '{tmp_path}'
        $seatDir = Join-Path $env:LOCALAPPDATA 'Bobiverse/worker/run/seats'
        New-Item -ItemType Directory -Force -Path $seatDir | Out-Null
        "MODE_JEEVES=" + (Get-BobTrayWorkerSeatMode (P 50 1 'bob-worker.exe' 'bob-worker.exe --mode jeeves'))
        "AGENT=" + (Measure-BobTrayWorkerSeats -Procs $mixed)
        "JEEVES_REF=[" + (Get-BobTrayWorkerCapRefusal -Procs $mixed -Mode jeeves) + "]"
        "AGENT_REF_NONEMPTY=" + [bool](Get-BobTrayWorkerCapRefusal -Procs $mixed -Mode agent)
        """
    )
    out = _ps(script)
    assert "MODE_JEEVES=jeeves" in out, out
    assert "AGENT=2" in out, out
    assert "JEEVES_REF=[]" in out, out
    assert "AGENT_REF_NONEMPTY=True" in out, out


def test_fr9640_watch_tray_jeeves_menu_uses_mode_jeeves():
    watch = WATCH_PS1.read_text(encoding="utf-8")
    assert "Start-BobTrayWorkerExe -Mode 'jeeves'" in watch
    assert "FR #9640" in watch
