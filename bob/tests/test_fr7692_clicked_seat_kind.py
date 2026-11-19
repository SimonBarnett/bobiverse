"""FR #7692: recycle restarts the clicked kind and refuses a seat with no click."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLICK = ROOT / "tray" / "tools" / "BobTrayClickedSeats.ps1"
RECYCLE = ROOT / "tray" / "tools" / "BobTrayRecycleSeat.ps1"
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
CS = ROOT / "tray" / "dialogs" / "BobTray.cs"


def _ps(script: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_fr7692_sources_keep_clicked_kind():
    watch = WATCH.read_text(encoding="utf-8")
    recycle = RECYCLE.read_text(encoding="utf-8")
    cs = CS.read_text(encoding="utf-8")
    assert "Add-BobTrayClickedSeat" in watch
    assert "param($seatNick, $kind, $model)" in watch
    assert "-Agent $kind" in watch
    assert "Mode 'agent' -Quiet -Trigger 'restore-after-recycle'" not in watch
    assert "kind-unknown" in recycle
    assert "Get-BobTrayClickedSeatKind" in recycle
    assert "RememberClickedSeat" in cs


def test_fr7692_recycle_restarts_opencode_and_refuses_unknown(tmp_path: Path):
    root = tmp_path / "root"
    (root / "run").mkdir(parents=True)
    rdir = root / "run" / "recycleseat"
    rdir.mkdir()
    expires = 4102444800
    (rdir / "req-a.json").write_text(
        json.dumps({"id": "a", "nick": "marchhare-4242", "by": "jeeves", "kind": "chair", "expires": expires}),
        encoding="ascii",
    )
    (rdir / "req-b.json").write_text(
        json.dumps({"id": "b", "nick": "marchhare-777", "by": "jeeves", "kind": "chair", "expires": expires}),
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
                "function Get-BobTraySeatPidFromNick { param($Nick) if ($Nick -eq 'marchhare-4242') { 4242 } else { 0 } }",
                "function Invoke-BobTrayRecycleSeatReportFailure { param($Root,$Site,$Exception) $script:reported = $Site }",
                "$script:reported = ''",
                f"Add-BobTrayClickedSeat -Root '{root}' -Nick 'marchhare-4242' -Kind 'opencode' -Machine 'marchhare'",
                "$script:kinds = New-Object System.Collections.Generic.List[string]",
                "$launch = { param($seatNick, $kind, $model) $script:kinds.Add([string]$kind); return 5050 }",
                f"$rows = @(Invoke-BobTrayRecycleSeatQueue -Root '{root}' -Dir '{rdir}' -Launch $launch -Log {{ param($m) }})",
                "$a = @($rows | Where-Object { $_.id -eq 'a' })[0]",
                "$b = @($rows | Where-Object { $_.id -eq 'b' })[0]",
                "$kind = @($script:kinds) -join ','",
                "if (-not $script:reported) { $script:reported = '-' }",
                "$line = ([string]$a.reason) + '|' + ([string]$a.ok) + '|' + $kind + '|' + ([string]$b.reason) + '|' + ([string]$script:reported)",
                f"Set-Content -LiteralPath '{log}' -Value $line -Encoding ascii",
            ]
        ),
        encoding="ascii",
    )
    proc = _ps(script)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert log.read_text(encoding="ascii").strip() == "ok|True|opencode|kind-unknown|-"
