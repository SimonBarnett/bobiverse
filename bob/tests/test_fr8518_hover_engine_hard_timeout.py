"""FR #8518: update-hover-engine must return after TimeoutSec even when Stop would hang."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tray" / "tools" / "BobTrayWarmStep.ps1"
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"


def test_fr8518_warm_step_abandons_without_sync_stop():
    text = HELPER.read_text(encoding="utf-8")
    assert "FR #8518" in text
    assert "Stop-BobTrayWarmEngineShellAsync" in text
    assert "BeginInvoke()" in text
    # Timeout path must not call $ps.Stop() synchronously on the poll thread.
    # The async helper may mention Stop inside its script string; the invoke
    # function itself must call the helper instead of $ps.Stop().
    fn_start = text.index("function Invoke-BobTrayWarmEngineStep")
    fn = text[fn_start:]
    nxt = fn.find("\nfunction ", 10)
    body = fn if nxt < 0 else fn[:nxt]
    assert "Stop-BobTrayWarmEngineShellAsync -Shell $ps" in body
    assert "$ps.Stop()" not in body


def test_fr8518_watch_does_not_bare_acquire_warm_shell():
    watch = WATCH.read_text(encoding="utf-8")
    assert "FR #8518: do not call Get-BobTrayWarmEngineShell bare" in watch
    # The old bare acquire before stall-alerts must be gone.
    window_start = watch.find("# FR #7660: warm runspace, 45s budget")
    assert window_start >= 0
    window = watch[window_start : window_start + 500]
    assert "[void](Get-BobTrayWarmEngineShell -Root $RepoRoot)" not in window
    assert "Invoke-BobTrayWarmEngineStep -Name 'stall-alerts'" in window


def test_fr8518_hung_warm_step_returns_within_budget(tmp_path: Path):
    log = tmp_path / "logs"
    log.mkdir()
    script = tmp_path / "run.ps1"
    # Body sleeps far past TimeoutSec. Sync Stop on a sleeping pipeline is usually
    # fast; the contract under test is wall-clock return + step-timeout log.
    script.write_text(
        "\n".join(
            [
                f". '{HELPER}'",
                f"$script:RepoRoot = '{tmp_path}'",
                "function Write-BobTrayEngineCycleLog {",
                "  param([string]$Message,[string]$Root)",
                f"  $p = Join-Path '{tmp_path}' 'logs\\tray-engine-cycle.log'",
                "  Add-Content -LiteralPath $p -Value ((Get-Date).ToString('o') + ' ' + $Message) -Encoding ascii",
                "}",
                "$sw = [Diagnostics.Stopwatch]::StartNew()",
                f"$r = Invoke-BobTrayWarmEngineStep -Name 'update-hover-engine' -Root '{tmp_path}' -TimeoutSec 2 -Body {{ Start-Sleep -Seconds 600 }}",
                "$sw.Stop()",
                "Write-Output ('{0}|{1}|{2:n2}' -f $r.timedOut.ToString(), $r.ok.ToString(), $sw.Elapsed.TotalSeconds)",
            ]
        ),
        encoding="ascii",
    )
    t0 = time.monotonic()
    r = subprocess.run(
        ["powershell", "-NoProfile", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    wall = time.monotonic() - t0
    assert r.returncode == 0, r.stdout + r.stderr
    line = [ln for ln in r.stdout.splitlines() if "|" in ln][-1]
    timed_out, ok, sec = line.split("|")
    assert timed_out == "True"
    assert ok == "False"
    assert float(sec.replace(",", ".")) < 12.0
    assert wall < 20.0
    log_text = (tmp_path / "logs" / "tray-engine-cycle.log").read_text(encoding="ascii")
    assert "step-start name=update-hover-engine" in log_text
    assert "step-timeout name=update-hover-engine" in log_text
