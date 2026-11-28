"""FR #10333: poll update-hover-engine must use Get-BobTrayHover -LocalOnly (45s budget)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"


def test_fr10333_update_hover_engine_local_only():
    watch = WATCH.read_text(encoding="utf-8-sig")
    idx = watch.index("-Name 'update-hover-engine'")
    window = watch[idx : idx + 1200]
    assert "Get-BobTrayHover -LocalOnly" in window
    assert "Get-BobTrayHover`n" not in window
    assert "Get-BobTrayHover -LocalOnly" in window
    full = watch[watch.index("Get-BobTrayHover -LocalOnly", idx) : watch.index("Get-BobTrayHover -LocalOnly", idx) + 60]
    assert "Get-BobTrayHover`n" not in full