"""FR #2928: Start-BobFleetTray.ps1 must be safe to dot-source (no tray tidy / process kill)."""
from __future__ import annotations

import re
import subprocess
import textwrap
from pathlib import Path

from repo_layout import resolve

FLEET = resolve("bob/tray/tools/Start-BobFleetTray.ps1")
if not FLEET.is_file():
    FLEET = resolve("third_party/bob-tray/tools/Start-BobFleetTray.ps1")


def test_fr2928_dotsource_guard_wraps_tidy_and_main():
    text = FLEET.read_text(encoding="utf-8-sig")
    assert text.endswith("\n") or text.endswith("\r\n")
    assert "FR #2928" in text
    assert "MyInvocation.InvocationName" in text
    assert "-eq '.'" in text or '-eq "."' in text
    guard_idx = text.find("MyInvocation.InvocationName")
    assert guard_idx > 0
    # Function def may precede the guard; call sites must be after it.
    calls = [
        m.start()
        for m in re.finditer(r"(?m)^\s*Invoke-BobSystrayTidy\b", text)
    ]
    assert calls, "expected Invoke-BobSystrayTidy call site"
    assert all(c > guard_idx for c in calls)
    # Stop/Cleanup helpers are only reached from Invoke-BobSystrayTidy (after guard).
    assert "Stop-BobSystrayPriorAgents" in text
    assert "Cleanup-OrphanAgents" in text


def test_fr2928_dotsource_does_not_emit_tidy(tmp_path):
    """Live: dot-source must not print tidy: Stop/Cleanup lines."""
    root = tmp_path / "bob"
    (root / "tools").mkdir(parents=True)
    (root / "tools" / "Watch-BobTray.ps1").write_text("# stub\n", encoding="utf-8")
    script = textwrap.dedent(
        f"""
        . '{FLEET}'
        Write-Output 'DOTSOURCE_OK'
        Write-Output ('HAS_ENSURE=' + [string][bool](Get-Command Ensure-BobSystraySeatWrapper -EA SilentlyContinue))
        """
    )
    r = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    assert "DOTSOURCE_OK" in out
    assert "HAS_ENSURE=True" in out
    assert "tidy:" not in out.lower()
    assert "Stop-BobSystrayPriorAgents" not in out
    assert "Cleanup-OrphanAgents" not in out
