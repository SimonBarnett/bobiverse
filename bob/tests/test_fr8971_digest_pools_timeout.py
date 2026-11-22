"""FR #8971: digest pool refresh cannot stall tray-status paint."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_fr8971_pools_child_has_15s_cap_and_single_flight():
    cs = (ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs").read_text(encoding="utf-8")
    assert "WaitForExit(15000)" in cs
    assert "digestPoolsPid" in cs
    assert "taskkill.exe" in cs
    assert "WaitForExit(25000)" not in cs


def test_fr8971_status_heartbeat_runs_before_hover():
    ps1 = (ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1").read_text(encoding="utf-8")
    dialogs = (ROOT / "bob" / "tray" / "tools" / "BobTrayDialogs.ps1").read_text(encoding="utf-8")
    assert "function Update-BobTrayStatusHeartbeat" in dialogs
    beat = ps1.index("Update-BobTrayStatusHeartbeat")
    hover = ps1.index("update-hover-engine", beat)
    assert beat < hover


def test_fr8971_unreachable_note_keeps_last_good_age():
    hover = (ROOT / "bob" / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1").read_text(encoding="utf-8")
    assert "last-good age=" in hover
