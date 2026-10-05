"""FR #2397: airc.exe PyInstaller build + MSI stage wiring."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_build_airc_ps1_exists_and_names_exe():
    p = ROOT / "scripts" / "Build-Airc.ps1"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "airc.exe" in text and "PyInstaller" in text and "2397" in text

def test_pack_airc_stages_bin_airc_exe():
    text = (ROOT / "scripts" / "Pack-AircConsoleRelease.ps1").read_text(encoding="utf-8")
    assert "Build-Airc.ps1" in text and "airc.exe" in text
