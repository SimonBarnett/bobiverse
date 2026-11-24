"""FR #9509: Start-BobTray prior sweep must not hang on bare Get-CimInstance Win32_Process."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

START = ROOT / "bob" / "scripts" / "Start-BobTray.ps1"
LIFE = ROOT / "bob" / "tray" / "tools" / "BobTrayLifecycle.ps1"
FLEET = ROOT / "bob" / "tray" / "tools" / "Start-BobFleetTray.ps1"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr9509_lifecycle_has_timed_prior_helper():
    t = _read(LIFE)
    assert "function Get-BobTrayPriorProcessHits" in t
    assert "EnumerationOptions" in t
    assert "Get-Process -Name 'bob-tray'" in t or 'Get-Process -Name "bob-tray"' in t
    assert "FR #9509" in t


def test_fr9509_start_bobtray_uses_timed_prior_not_bare_cim():
    t = _read(START)
    assert "FR #9509" in t
    assert "Get-BobTrayPriorProcessHits" in t
    # Bare prior census must not remain as the only path.
    prior = t.split("# One TipForm only", 1)[1].split("Prefer Start-BobFleetTray", 1)[0]
    assert "Get-BobTrayPriorProcessHits" in prior
    # No live bare Get-CimInstance call in the prior block (comment mentioning it is ok).
    live_lines = [
        ln
        for ln in prior.splitlines()
        if "Get-CimInstance Win32_Process" in ln and not ln.lstrip().startswith("#")
    ]
    assert live_lines == [], live_lines


def test_fr9509_fleet_tray_processes_prefer_timed_helper():
    t = _read(FLEET)
    fn = t[t.find("function Get-BobSystrayTrayProcesses") :]
    fn = fn[: fn.find("\nfunction ")] if "\nfunction " in fn[1:] else fn
    assert "FR #9509" in fn
    assert "Get-BobTrayPriorProcessHits" in fn or "EnumerationOptions" in fn
    assert "Get-Process -Name 'bob-tray'" in fn or 'Get-Process -Name "bob-tray"' in fn
