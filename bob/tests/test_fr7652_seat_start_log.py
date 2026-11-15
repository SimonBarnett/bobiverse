"""FR #7652: every tray seat start writes trigger, seat id, and worker pid."""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tray" / "tools" / "BobTrayStartWorker.ps1"
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"

TRIGGERS = ("menu", "auto-start", "restore-after-recycle", "named-other-path")


def test_fr7652_each_trigger_writes_a_seat_start_line(tmp_path: Path):
    log = tmp_path / "watch_bob_tray.log"
    script = tmp_path / "run.ps1"
    calls = "\n".join(
        (
            "Write-BobTraySeatStart -Log ${function:Write-TrayLog} "
            f"-SeatId 'seat-{i}' -WorkerPid {1000 + i} -Trigger '{trig}'"
        )
        for i, trig in enumerate(TRIGGERS)
    )
    script.write_text(
        "\n".join(
            [
                f". '{HELPER}'",
                f"$logPath = '{log}'",
                "function Write-TrayLog([string]$m) {",
                "  Add-Content -Path $logPath -Value ('{0:o} {1}' -f [datetime]::UtcNow, $m) -Encoding ascii",
                "}",
                calls,
                "Write-BobTraySeatStart -Log ${function:Write-TrayLog} -SeatId 'Bearer EXAMPLE' -WorkerPid 9 -Trigger 'menu'",
            ]
        ),
        encoding="utf-8",
    )
    r = subprocess.run(
        ["powershell", "-NoProfile", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    text = log.read_text(encoding="utf-8")
    for trig in TRIGGERS:
        assert f"trigger={trig}" in text, text
    assert "seat-start seat=" in text
    assert "pid=" in text
    assert "Bearer" not in text
    assert "EXAMPLE" not in text
    # Write-TrayLog stamps an ISO-8601 timestamp before the message.
    assert "T" in text.splitlines()[0]


def test_fr7652_tray_call_sites_name_each_trigger():
    w = WATCH.read_text(encoding="utf-8")
    assert "-Trigger 'menu'" in w
    assert "-Trigger 'auto-start'" in w
    assert "-Trigger 'restore-after-recycle'" in w
    assert "Write-BobTraySeatStart" in w
    body = w[w.index("function Start-BobTrayWorkerExe"): w.index("$script:attention = $false")]
    assert "[string]$Trigger" in body
    assert "seat-start" not in body or "Write-BobTraySeatStart" in body
