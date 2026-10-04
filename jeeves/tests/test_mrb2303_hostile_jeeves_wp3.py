"""MRB #2303 hostile: FR #2301 WP3 encoding + pack/install contract."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

BUILD = ROOT / "jeeves/scripts/Build-Jeeves.ps1"
PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
INSTALL = ROOT / "jeeves/scripts/Install-Jeeves.ps1"
DOC = ROOT / "jeeves/docs/jeeves-exe-self-heal.md"
TEST = ROOT / "jeeves/tests/test_fr2301_jeeves_exe_wp3.py"

MOJIBAKE_DASH = ("\u00e2" + "\u20ac")


def _assert_utf8_no_bom(path: Path, *, allow_needle_file: bool = False) -> None:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n"), path
    text = raw.decode("utf-8")
    assert "\ufeff" not in text, path
    if not allow_needle_file:
        assert MOJIBAKE_DASH not in text, path


def test_mrb2303_wp3_files_utf8_no_bom():
    for p in (BUILD, PACK, INSTALL, DOC):
        assert p.is_file(), p
        _assert_utf8_no_bom(p)
    assert TEST.is_file()
    _assert_utf8_no_bom(TEST, allow_needle_file=True)


def test_mrb2303_pack_resolves_build_jeeves_and_stages_under_jeeves_dir():
    text = PACK.read_text(encoding="utf-8")
    assert "scripts\\Build-Jeeves.ps1" in text or "scripts/Build-Jeeves.ps1" in text
    assert "jeeves\\jeeves.exe" in text or "jeeves\\\\jeeves.exe" in text
    assert "SkipJeevesExe" in text
    assert "-SkipMsi" in text


def test_mrb2303_install_cutover_unregisters_callback_when_exe_present():
    text = INSTALL.read_text(encoding="utf-8")
    assert "Unregister-ScheduledTask" in text
    assert "BobCallback" in text
    assert "$useJeevesExe" in text
    assert "--chair --http 127.0.0.1:7700" in text
