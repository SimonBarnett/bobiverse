"""BOB-40: Agents > Jeeves uses jeeves/assets/jeeves-butler.ico."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ICO = ROOT / "jeeves" / "assets" / "jeeves-butler.ico"
CS = (ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs").read_text(encoding="utf-8")
WATCH = (ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1").read_text(encoding="utf-8")
DOC = (ROOT / "bob" / "docs" / "bob-40-jeeves-butler-icon.md").read_text(encoding="utf-8")


def test_fr8678_butler_icon_path():
    raw = ICO.read_bytes()
    assert raw[:4] == b"\x00\x00\x01\x00"
    assert "jeeves-butler.ico" in CS
    assert "miJeeves.Image" in CS
    assert "jeeves-butler.ico" in WATCH
    assert "$miJeeves.Image" in WATCH
    assert "jeeves/assets/jeeves-butler.ico" in DOC
    assert "jeeves-icon" in DOC
