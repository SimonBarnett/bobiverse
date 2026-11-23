"""FR #8694 / BOB-54: Agents > Priority uses the existing priority.ico."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ICO = ROOT / "bob" / "vendor" / "priority" / "priority.ico"
CS = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
PS1 = ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"


def test_priority_icon_is_existing_ico_and_pinned():
    data = ICO.read_bytes()
    assert data[:4] == b"\x00\x00\x01\x00"
    cs = CS.read_text(encoding="utf-8")
    ps1 = PS1.read_text(encoding="utf-8")
    assert "vendor/priority/priority.ico" in cs
    assert "vendor\\\\priority\\\\priority.ico" in cs
    assert "priority-icon path=vendor/priority/priority.ico" in ps1
    assert "vendor\\priority\\priority.ico" in ps1
