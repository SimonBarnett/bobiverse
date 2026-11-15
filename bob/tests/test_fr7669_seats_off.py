"""FR #7669: seat_target 0 blocks engine and menu seat starts."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START = ROOT / "tray" / "tools" / "BobTrayStartWorker.ps1"
RECYCLE = ROOT / "tray" / "tools" / "BobTrayRecycleSeat.ps1"
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
TRAY = ROOT / "tray" / "dialogs" / "BobTray.cs"
IRC = ROOT / "tray" / "src" / "Private" / "Get-BobIrc.ps1"


def _ps(script: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )


def test_fr7669_sources_gate_every_start_path():
    start = START.read_text(encoding="utf-8")
    watch = WATCH.read_text(encoding="utf-8")
    recycle = RECYCLE.read_text(encoding="utf-8")
    tray = TRAY.read_text(encoding="utf-8")
    irc = IRC.read_text(encoding="utf-8")
    assert "function Test-BobTraySeatsOff" in start
    assert "seats-off" in start
    assert "Seats are off on this machine" in watch
    assert "seat target 0" in watch
    assert "seats-off" in recycle
    assert "Stop-BobWorkerSeatTrees" in recycle
    # Recycle must refuse before it stops a live seat.
    assert recycle.index("seats-off") < recycle.index("Stop-BobWorkerSeatTrees")
    assert "Seats: off (seat target 0)" in tray
    assert "WorkerLauncher.SeatsOff" in tray
    assert tray.index("Seats are off on this machine") < tray.index("LaunchCalls++")
    assert "seat_target" in irc
    assert "seats off" in watch


def test_fr7669_engine_cycle_starts_nothing_then_resumes(tmp_path: Path):
    bridge = tmp_path / "bridge"
    bridge.mkdir()
    cfg = bridge / "config.json"
    cfg.write_text(json.dumps({"seat_target": 0}), encoding="utf-8")
    qdir = tmp_path / "startworker"
    qdir.mkdir()
    rdir = tmp_path / "recycleseat"
    rdir.mkdir()
    expires = 4102444800
    (qdir / "req-a.json").write_text(
        json.dumps({"id": "a", "mode": "agent", "by": "test", "expires": expires}),
        encoding="utf-8",
    )
    (rdir / "req-b.json").write_text(
        json.dumps({"id": "b", "nick": "marchhare-1", "by": "test", "expires": expires}),
        encoding="utf-8",
    )
    log = tmp_path / "out.txt"
    script = tmp_path / "run.ps1"
    script.write_text(
        "\n".join(
            [
                f"$env:BOB_BRIDGE_HOME = '{bridge}'",
                f". '{START}'",
                f". '{RECYCLE}'",
                "$script:launches = 0",
                "$launch = { param($mode, $agent) $script:launches++; return 4242 }",
                f"$q = Invoke-BobTrayStartWorkerQueue -Dir '{qdir}' -Launch $launch -Log {{ param($m) }}",
                f"$r = Invoke-BobTrayRecycleSeatQueue -Root '{tmp_path}' -Dir '{rdir}' -Launch $launch -Log {{ param($m) }}",
                f"Set-Content -LiteralPath '{log}' -Value (@($q.reason, $r.reason, $script:launches) -join '|') -Encoding ascii",
            ]
        ),
        encoding="utf-8",
    )
    first = _ps(script)
    assert first.returncode == 0, first.stdout + first.stderr
    assert log.read_text(encoding="ascii").strip() == "seats-off|seats-off|0"
    cfg.write_text(json.dumps({"profiles": {}}), encoding="utf-8")
    (qdir / "req-c.json").write_text(
        json.dumps({"id": "c", "mode": "agent", "by": "test", "expires": expires}),
        encoding="utf-8",
    )
    script2 = tmp_path / "run2.ps1"
    script2.write_text(
        "\n".join(
            [
                f"$env:BOB_BRIDGE_HOME = '{bridge}'",
                f". '{START}'",
                "function Get-BobTrayWorkerCapRefusal { return '' }",
                "$script:launches = 0",
                "$launch = { param($mode, $agent) $script:launches++; return 7 }",
                f"$q = Invoke-BobTrayStartWorkerQueue -Dir '{qdir}' -Launch $launch -Log {{ param($m) }}",
                f"Set-Content -LiteralPath '{log}' -Value (@($q.reason, $q.pid, $script:launches) -join '|') -Encoding ascii",
            ]
        ),
        encoding="utf-8",
    )
    second = _ps(script2)
    assert second.returncode == 0, second.stdout + second.stderr
    assert log.read_text(encoding="ascii").strip() == "|7|1"


def test_fr7669_mrb_plan_mode_not_blocked_when_seats_off(tmp_path: Path):
    """Hostile: plan starts must keep working while seat_target is 0."""
    bridge = tmp_path / "bridge"
    bridge.mkdir()
    (bridge / "config.json").write_text(json.dumps({"seat_target": 0}), encoding="utf-8")
    qdir = tmp_path / "startworker"
    qdir.mkdir()
    expires = 4102444800
    (qdir / "req-plan.json").write_text(
        json.dumps({"id": "plan1", "mode": "plan", "by": "test", "expires": expires}),
        encoding="utf-8",
    )
    log = tmp_path / "out.txt"
    script = tmp_path / "run-plan.ps1"
    script.write_text(
        "\n".join(
            [
                f"$env:BOB_BRIDGE_HOME = '{bridge}'",
                f". '{START}'",
                "function Get-BobTrayWorkerCapRefusal { return '' }",
                "$script:launches = 0",
                "$launch = { param($mode, $agent) $script:launches++; return 99 }",
                f"$q = Invoke-BobTrayStartWorkerQueue -Dir '{qdir}' -Launch $launch -Log {{ param($m) }}",
                f"Set-Content -LiteralPath '{log}' -Value (@($q.ok, $q.reason, $q.pid, $script:launches) -join '|') -Encoding ascii",
            ]
        ),
        encoding="utf-8",
    )
    proc = _ps(script)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert log.read_text(encoding="ascii").strip() == "True||99|1"


def test_fr7669_mrb_csharp_gate_and_digest_hooks():
    """Hostile: C# SeatsOff + digest/hover/tile paint stay wired."""
    tray = TRAY.read_text(encoding="utf-8")
    watch = WATCH.read_text(encoding="utf-8")
    irc = IRC.read_text(encoding="utf-8")
    hover = (ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1").read_text(encoding="utf-8")
    assert "public static bool SeatsOff()" in tray
    assert "seat_target" in tray
    assert "Regex.IsMatch(" in tray
    assert 'string.Equals(mode, "agent"' in tray
    assert "WorkerLauncher.SeatsOff()" in tray
    assert "seat_target" in irc
    assert "seat_target" in hover
    assert "seats off" in watch
    assert "menu.Opening" in tray
    assert "Seats: off (seat target 0)" in tray


def test_fr7669_mrb_missing_key_allows_agent_start(tmp_path: Path):
    """Hostile: removing seat_target (or never setting it) must resume agent starts."""
    bridge = tmp_path / "bridge"
    bridge.mkdir()
    (bridge / "config.json").write_text(json.dumps({"profiles": {}}), encoding="utf-8")
    qdir = tmp_path / "startworker"
    qdir.mkdir()
    expires = 4102444800
    (qdir / "req-a.json").write_text(
        json.dumps({"id": "a", "mode": "agent", "by": "test", "expires": expires}),
        encoding="utf-8",
    )
    log = tmp_path / "out.txt"
    script = tmp_path / "run-missing.ps1"
    script.write_text(
        "\n".join(
            [
                f"$env:BOB_BRIDGE_HOME = '{bridge}'",
                f". '{START}'",
                "function Get-BobTrayWorkerCapRefusal { return '' }",
                "$script:launches = 0",
                "$launch = { param($mode, $agent) $script:launches++; return 3 }",
                f"$q = Invoke-BobTrayStartWorkerQueue -Dir '{qdir}' -Launch $launch -Log {{ param($m) }}",
                f"Set-Content -LiteralPath '{log}' -Value (@($q.ok, $q.reason, $script:launches) -join '|') -Encoding ascii",
            ]
        ),
        encoding="utf-8",
    )
    proc = _ps(script)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert log.read_text(encoding="ascii").strip() == "True||1"

