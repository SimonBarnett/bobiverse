"""FR #8321: a restarted seat keeps the exact model Si clicked (paid or free)."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import bob.scripts.bob_worker as bw

ROOT = Path(__file__).resolve().parents[1]
CLICK = ROOT / "tray" / "tools" / "BobTrayClickedSeats.ps1"
RECYCLE = ROOT / "tray" / "tools" / "BobTrayRecycleSeat.ps1"
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
CS = ROOT / "tray" / "dialogs" / "BobTray.cs"

GO = "opencode-go/deepseek-v4-pro"
FREE = "opencode/deepseek-v4.1-flash-free"


def _ps(script: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _isolate_tray(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("BOB_WORKER_START_MODEL_FILE", raising=False)
    monkeypatch.delenv("BOB_WORKER_START_MODEL_JSON", raising=False)
    monkeypatch.delenv("BOB_SEAT_MODEL_PIN", raising=False)


def test_fr8321_clicked_record_carries_model():
    watch = WATCH.read_text(encoding="utf-8")
    recycle = RECYCLE.read_text(encoding="utf-8")
    click = CLICK.read_text(encoding="utf-8")
    cs = CS.read_text(encoding="utf-8")
    assert "Get-BobTrayClickedSeatModel" in click
    assert "Get-BobTrayClickedLaunchModel" in click
    assert "-Model $recModel" in watch
    assert "param($seatNick, $kind, $model)" in watch
    assert "BOB_SEAT_MODEL_PIN" in watch
    assert "-SessionEnv $restoreEnv" in watch
    assert "Get-BobTrayClickedSeat -Root $Root -Nick $seatNick" in recycle
    assert "& $Launch $seatNick $clickedKind $clickedModel" in recycle
    assert "ResolveClickedSeatModel" in cs
    assert "RememberClickedSeat" in cs


def test_fr8321_clicked_seats_ps_round_trip(tmp_path: Path):
    root = tmp_path / "root"
    log = tmp_path / "out.txt"
    script = tmp_path / "t.ps1"
    script.write_text(
        "\n".join(
            [
                f". '{CLICK}'",
                f"Add-BobTrayClickedSeat -Root '{root}' -Nick 'm-1' -Kind 'opencode' -Machine 'm' -Model '{GO}'",
                f"Add-BobTrayClickedSeat -Root '{root}' -Nick 'm-2' -Kind 'grok' -Machine 'm' -Model 'EXAMPLE_GROK_MAX'",
                f"$p = Get-BobTrayClickedSeatPath -Root '{root}'",
                "$legacy = 'm-3' + \"`t\" + 'cursor' + \"`t\" + 'm'",
                "Add-Content -LiteralPath $p -Value $legacy -Encoding ascii",
                "$a = Get-BobTrayClickedSeat -Root '{0}' -Nick 'm-1'".format(root),
                "$b = Get-BobTrayClickedSeatModel -Root '{0}' -Nick 'm-2'".format(root),
                "$c = Get-BobTrayClickedSeat -Root '{0}' -Nick 'm-3'".format(root),
                "$line = $a.Kind + '|' + $a.Model + '|' + $b + '|' + $c.Kind + '|' + [string]$c.Model + '|' + (Get-BobTrayClickedSeatKind -Root '{0}' -Nick 'm-1')".format(root),
                f"Set-Content -LiteralPath '{log}' -Value $line -Encoding ascii",
            ]
        ),
        encoding="ascii",
    )
    proc = _ps(script)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert log.read_text(encoding="ascii").strip() == f"opencode|{GO}|EXAMPLE_GROK_MAX|cursor||opencode"


def test_fr8321_recycle_passes_clicked_model(tmp_path: Path):
    root = tmp_path / "root"
    (root / "run").mkdir(parents=True)
    rdir = root / "run" / "recycleseat"
    rdir.mkdir()
    (rdir / "req-a.json").write_text(
        json.dumps(
            {"id": "a", "nick": "m-4242", "by": "jeeves", "kind": "chair", "expires": 4102444800}
        ),
        encoding="ascii",
    )
    log = tmp_path / "out.txt"
    script = tmp_path / "run.ps1"
    script.write_text(
        "\n".join(
            [
                f". '{CLICK}'",
                f". '{RECYCLE}'",
                "function Test-BobTraySeatsOff { $false }",
                "function Test-BobTrayPidAlive { param($ProcessId) $false }",
                "function Stop-BobWorkerSeatTrees { param($RootPids) }",
                "function Get-BobTraySeatMarkerPid { param($Nick) 0 }",
                "function Get-BobTraySeatPidFromNick { param($Nick) 4242 }",
                "function Invoke-BobTrayRecycleSeatReportFailure { param($Root,$Site,$Exception) }",
                f"Add-BobTrayClickedSeat -Root '{root}' -Nick 'm-4242' -Kind 'opencode' -Machine 'm' -Model '{GO}'",
                "$launch = { param($seatNick, $kind, $model) $script:got = ([string]$kind) + '|' + ([string]$model); return 5050 }",
                f"$rows = @(Invoke-BobTrayRecycleSeatQueue -Root '{root}' -Dir '{rdir}' -Launch $launch -Log {{ param($m) }})",
                "$a = @($rows | Where-Object { $_.id -eq 'a' })[0]",
                "$line = ([string]$a.reason) + '|' + ([string]$a.ok) + '|' + $script:got",
                f"Set-Content -LiteralPath '{log}' -Value $line -Encoding ascii",
            ]
        ),
        encoding="ascii",
    )
    proc = _ps(script)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert log.read_text(encoding="ascii").strip() == f"ok|True|opencode|{GO}"


def test_fr8321_pinned_paid_paused_does_not_switch_to_free(tmp_path, monkeypatch):
    """A paused paid pin stays the opened weight. It does not fall through to free."""
    _isolate_tray(monkeypatch, tmp_path)
    bw._OPENCODE_MODEL_ENV_AT_START = GO
    state = tmp_path / "state"
    now = 2_000_000.0
    bw.opencode_fuel.save_opencode_pauses(state, {GO: now + 3600})
    env = dict(os.environ)
    env["BOB_OPENCODE_MODEL"] = GO
    env["BOB_SEAT_MODEL_PIN"] = "1"
    fuel = bw.Fuel(opencode_free=100, opencode_free_model_ids=(FREE,))
    logs: list[str] = []
    got = bw.resolve_opencode_model(fuel, state_dir=state, now=now, env=env, log_fn=logs.append)
    assert got == GO


def test_fr8321_pinned_free_stays_free(tmp_path, monkeypatch):
    _isolate_tray(monkeypatch, tmp_path)
    bw._OPENCODE_MODEL_ENV_AT_START = FREE
    env = dict(os.environ)
    env["BOB_OPENCODE_MODEL"] = FREE
    env["BOB_SEAT_MODEL_PIN"] = "1"
    fuel = bw.Fuel(opencode_free=100, opencode_free_model_ids=(FREE,))
    got = bw.resolve_opencode_model(fuel, state_dir=tmp_path / "state", env=env)
    assert got == FREE


def test_fr8321_pinned_paid_stays_paid_while_free_remains(tmp_path, monkeypatch):
    """The paid model the operator opened stays selected while free remains."""
    _isolate_tray(monkeypatch, tmp_path)
    bw._OPENCODE_MODEL_ENV_AT_START = GO
    env = dict(os.environ)
    env["BOB_OPENCODE_MODEL"] = GO
    env["BOB_SEAT_MODEL_PIN"] = "1"
    fuel = bw.Fuel(opencode_free=100, opencode_free_model_ids=(FREE,))
    logs: list[str] = []
    got = bw.resolve_opencode_model(
        fuel, state_dir=tmp_path / "state", env=env, log_fn=logs.append
    )
    assert got == GO
    assert any("source=env" in line for line in logs)


def test_fr8321_seat_model_pin_env_values():
    assert bw.seat_model_pinned({"BOB_SEAT_MODEL_PIN": "1"}) is True
    assert bw.seat_model_pinned({"BOB_SEAT_MODEL_PIN": "true"}) is True
    assert bw.seat_model_pinned({"BOB_SEAT_MODEL_PIN": "0"}) is False
    assert bw.seat_model_pinned({}) is False
