"""FR #5522: Invoke-AircExtensionGpo.ps1 must resolve under frozen airc.exe / install tree."""
from __future__ import annotations

import sys
from pathlib import Path

import airc_extension as ex
from repo_layout import ROOT


def test_fr5522_source_tree_script_present():
    p = ex.gpo_script_path()
    assert p.is_file()
    assert p.name == "Invoke-AircExtensionGpo.ps1"


def test_fr5522_meipass_candidate_wins_when_frozen(tmp_path, monkeypatch):
    mei = tmp_path / "_MEIxxxx"
    mei.mkdir()
    bundled = mei / "Invoke-AircExtensionGpo.ps1"
    bundled.write_text("# bundled gpo\n", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(mei), raising=False)
    # Prefer MEIPASS over a missing beside-__file__ probe via install_root empty.
    got = ex.gpo_script_path()
    assert got.resolve() == bundled.resolve()


def test_fr5522_install_airc_scripts_layout(tmp_path, monkeypatch):
    """Issue: install ships under <root>\\airc\\scripts — must be searched."""
    root = tmp_path / "ai" / "airc"
    nested = root / "airc" / "scripts"
    nested.mkdir(parents=True)
    target = nested / "Invoke-AircExtensionGpo.ps1"
    target.write_text("# install tree\n", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setenv("AIRC_INSTALL_ROOT", str(root))
    # Hide the real source script by preferring env roots first when frozen.
    got = ex.gpo_script_path()
    assert got.resolve() == target.resolve()


def test_fr5522_build_airc_adds_gpo_ps1_data():
    build = (ROOT / "airc" / "scripts" / "Build-Airc.ps1").read_text(encoding="utf-8")
    assert "Invoke-AircExtensionGpo.ps1" in build
    assert "--add-data" in build
