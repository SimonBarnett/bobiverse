"""FR #3180: worker seat starts are manual only — no tray seat-heal auto-start/respawn.

Acceptance (must fail on pre-3180 main that still heals):
- Watchdog never reaches WorkerLauncher.Launch / HealWorkerSeats.
- Ensure-BobWorkerSeats.ps1 never writes req-*.json (report-only).
- Idle stale-build keeps the seat running (no EXIT_STALE_BUILD) and announces.
- Docs/skills say manual only (Agent/Plan / !startworker / human bob-worker).
"""
from __future__ import annotations

import re
import subprocess
import textwrap
from pathlib import Path

import bob_worker as bw
from repo_layout import ROOT

BOB_TRAY = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
ENSURE = ROOT / "bob" / "scripts" / "Ensure-BobWorkerSeats.ps1"
POST = ROOT / "common" / "docs" / "post-install.md"
SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
WORKER_PY = ROOT / "bob" / "scripts" / "bob_worker.py"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def _watchdog_body(src: str) -> str:
    i = src.find("void Watchdog()")
    assert i >= 0, "Watchdog missing"
    rest = src[i:]
    nxt = rest.find("\n        void ", 1)
    return rest if nxt < 0 else rest[:nxt]


def test_fr3180_watchdog_never_launches_or_heals_seats():
    t = _read(BOB_TRAY)
    wd = _watchdog_body(t)
    assert "HealEngine()" in wd
    assert "HealWorkerSeats" not in wd
    assert "WorkerLauncher.Launch" not in wd
    assert 'Launch(root, "agent"' not in wd
    # No HealWorkerSeats method left that auto-starts.
    assert "void HealWorkerSeats" not in t
    # SeatHealEnabled must not default-on heal (removed or always-off unused).
    if "SeatHealEnabled" in t:
        body = t[t.find("SeatHealEnabled") :]
        body = body[: body.find("}", 1) + 1]
        assert "return true" not in body.replace(" ", "")


def test_fr3180_watchdog_observes_seat_exit_without_restart():
    t = _read(BOB_TRAY)
    wd = _watchdog_body(t)
    assert "ObserveWorkerSeats" in wd or "seat-exit" in t
    assert "seat-exit" in t
    assert "not restarted" in t


def test_fr3180_watchdog_ticks_harness_exists():
    t = _read(BOB_TRAY)
    assert "--watchdog-ticks" in t
    assert "LaunchCalls" in t or "launch_calls" in t.lower() or "launches=" in t


def test_fr3180_ensure_report_only_never_queues_req(tmp_path):
    assert ENSURE.is_file()
    ens = _read(ENSURE)
    assert "FR #3180" in ens or "report-only" in ens.lower() or "manual only" in ens.lower()
    # Must not write startworker req files.
    assert "req-" not in ens or "never" in ens.lower()
    assert "Set-Content" not in ens or "DryRun" in ens
    # Live: with 0 seats, script must not create req-*.json.
    root = tmp_path / "bob"
    tools = root / "tools"
    tools.mkdir(parents=True)
    # Minimal stubs so Ensure can measure without real tray helpers.
    start = root / "tools" / "BobTrayStartWorker.ps1"
    start.write_text(
        textwrap.dedent(
            """
            $script:BobTrayHardMaxWorkers = 2
            function Measure-BobTrayWorkerSeats { param($Procs,$Modes) 0 }
            function Get-BobTrayWorkerCapRefusal { param($Mode) $null }
            function Get-BobTrayStartWorkerDir { param($Root) Join-Path $Root 'run\\startworker' }
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    # Prefer tools path used by Ensure
    dest_scripts = root / "scripts"
    dest_scripts.mkdir(parents=True)
    ensure_copy = dest_scripts / "Ensure-BobWorkerSeats.ps1"
    ensure_copy.write_text(ENSURE.read_text(encoding="utf-8-sig"), encoding="utf-8")
    sw_dir = root / "run" / "startworker"
    sw_dir.mkdir(parents=True)
    # Point Ensure at this root; its $PSScriptRoot is scripts/
    r = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ensure_copy),
            "-RepoRoot",
            str(root),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    reqs = list(sw_dir.glob("req-*.json"))
    assert reqs == [], f"Ensure must not queue req files; got {reqs}; out={out}"


def test_fr3180_idle_stale_keeps_running_announces(tmp_path):
    class _Irc:
        def __init__(self):
            self.alive = True
            self.shop = "#marchhare"
            self.said = []

        def say(self, target, text):
            self.said.append((target, text))
            return True

        def close(self, why=""):
            self.alive = False

    logs: list = []
    relay = bw.Relay(logs.append, persist_dir=tmp_path)
    irc = _Irc()
    sup = bw.Supervisor(
        kind="grok",
        exe=r"C:\x\agent.exe",
        cwd=str(tmp_path),
        machine="marchhare",
        nick="marchhare-4242",
        run_dir=tmp_path,
        irc=irc,
        relay=relay,
        log=logs.append,
        bored=None,
    )
    sup.stale_build_check = lambda: "run=old install=new"
    assert sup.post_bored() is False
    assert ("#marchhare", "!bored") not in irc.said
    assert not sup.done.wait(0.3), "stale seat must keep running (no EXIT_STALE_BUILD)"
    assert getattr(sup, "exit_code", None) in (None, 0) or not hasattr(sup, "exit_code") or sup.exit_code != bw.EXIT_STALE_BUILD
    assert any("stale build" in m.lower() for m in logs)
    assert any("manual" in m.lower() or "restart" in m.lower() for m in logs) or any(
        "manual" in str(s).lower() or "restart" in str(s).lower() for s in irc.said
    )


def test_fr3180_exit_no_agent_still_exits_without_heal_docs():
    t = _read(WORKER_PY)
    assert "EXIT_NO_AGENT = 4" in t
    assert "no key given - not starting" in t
    # Product docs must not promise seat-heal after Cancel / EXIT_NO_AGENT.
    skill = _read(SKILL)
    assert "manual only" in skill.lower() or "manual-only" in skill.lower() or "FR #3180" in skill
    assert "HealWorkerSeats" not in skill


def test_fr3180_docs_manual_only():
    post = _read(POST)
    skill = _read(SKILL)
    blob = post + "\n" + skill
    assert "FR #3180" in blob
    assert re.search(r"manual only|manual-only", blob, re.I)
    # Old auto top-up promise must be gone or superseded.
    assert "HealWorkerSeats" not in skill
    assert "tops agent seats back up" not in post.lower()
