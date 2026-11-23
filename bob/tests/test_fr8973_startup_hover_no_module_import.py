"""FR #8973: startup hover must not Import-Module inside the timed job."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"


def test_fr8973_startup_returns_without_import_module():
    watch = WATCH.read_text(encoding="utf-8-sig")
    start = watch.index("-Name 'startup-update-hover' -Root $RepoRoot")
    window = watch[start:start + 1800]
    assert "Import-Module `$psd1 -Force" not in window
    assert "Get-Command Get-BobTrayHover -ErrorAction SilentlyContinue" in window
    assert "Get-BobTrayHover -LocalOnly" in window
    assert window.index("if (-not (Get-Command Get-BobTrayHover") < window.index("Get-BobTrayHover -LocalOnly")
