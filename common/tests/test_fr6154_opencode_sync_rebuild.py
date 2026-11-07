"""FR #6154: Sync/ff + pack path ships OpenCode fuel helpers and worker markers.

Live installs can keep a pre-#6120 Get-BobAgentFuel.ps1 when Sync robocopy uses /XO
on bob tray tools/ (git checkout mtimes older than the flat copy). Pack/Sync must force
bob tray tools (same bar as FR #269 scripts) and include bob-setup-opencode + opencode markers.
MRB #6162: no-/XO is Product=bob tools only; jeeves tools keep /XO.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from repo_layout import ROOT

SYNC = ROOT / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1"
PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
BUILD = ROOT / "bob" / "scripts" / "Build-BobWorker.ps1"
AGENT_FUEL = ROOT / "bob" / "tray" / "tools" / "Get-BobAgentFuel.ps1"
OPENCODE_FUEL_PS1 = ROOT / "bob" / "tray" / "tools" / "Get-BobOpencodeFuel.ps1"
OPENCODE_FUEL_PY = ROOT / "common" / "scripts" / "opencode_fuel.py"
WORKER = ROOT / "bob" / "scripts" / "bob_worker.py"
SKILL = ROOT / "bob" / ".grok" / "skills" / "bob-setup-opencode" / "SKILL.md"


def _sync() -> str:
    return SYNC.read_text(encoding="utf-8-sig")


def test_fr6154_source_assets_present_with_opencode():
    assert AGENT_FUEL.is_file()
    assert OPENCODE_FUEL_PS1.is_file()
    assert OPENCODE_FUEL_PY.is_file()
    assert SKILL.is_file()
    assert "opencode" in AGENT_FUEL.read_text(encoding="utf-8-sig").lower()
    assert "opencode" in OPENCODE_FUEL_PS1.read_text(encoding="utf-8-sig").lower()
    assert "opencode" in WORKER.read_text(encoding="utf-8").lower()


def test_fr6154_sync_bob_tray_tools_no_xo_jeeves_keeps_xo():
    """Bob tools force-refresh; jeeves tools still use /XO (MRB #6162)."""
    text = _sync()
    assert "FR #6154" in text
    assert "tools-no-xo" in text.lower()
    assert "third_party\\bob-tray\\tools" in text or "third_party\bob-tray\tools" in text
    # Gate must be Product=bob AND Dst tools --- not bare Dst -eq tools.
    assert "$Product -eq 'bob' -and $m.Dst -eq 'tools'" in text
    # Jeeves still has a tools mirror entry.
    assert "Product -eq 'jeeves'" in text and "Dst = 'tools'" in text


def test_fr6154_sync_includes_bob_setup_opencode_skill_for_bob_only():
    text = _sync()
    assert "$Product -eq 'bob' -and $_.Name -eq 'bob-setup-opencode'" in text


def test_fr6154_worker_source_has_opencode_decision_markers():
    src = WORKER.read_text(encoding="utf-8")
    assert "opencode_has_tokens" in src
    assert "select_agent" in src
    assert "opencode" in src
    assert "dry-run" in src or "dry_run" in src


def test_fr6154_pack_stages_tray_tools_and_builds_worker():
    pack = PACK.read_text(encoding="utf-8-sig")
    assert "Build-BobWorker.ps1" in pack
    assert "bob-worker.exe" in pack
    assert "third_party\\bob-tray" in pack or "third_party\bob-tray" in pack or "bob\\tray" in pack or "bob\tray" in pack
    build = BUILD.read_text(encoding="utf-8-sig")
    assert "--dry-run" in build
    assert "bob_worker.py" in build


def test_fr6154_pre6120_marker_absent_means_fail_probe():
    """Build smoke requires decision JSON; rebuilt exe must embed OpenCode selection (Pack)."""
    build = BUILD.read_text(encoding="utf-8-sig")
    assert '"decision"' in build or "'decision'" in build


def _robo(src: Path, dst: Path, *extra: str) -> int:
    args = [
        "robocopy.exe",
        str(src),
        str(dst),
        "/E",
        *extra,
        "/NFL",
        "/NDL",
        "/NJH",
        "/NJS",
        "/nc",
        "/ns",
        "/np",
    ]
    r = subprocess.run(args, capture_output=True, text=True)
    # robocopy 0-7 = success-ish
    return r.returncode


@pytest.mark.skipif(sys.platform != "win32", reason="robocopy hermetic pin is Windows-only")
def test_fr6154_hermetic_robocopy_xo_vs_force(tmp_path: Path):
    """Without /XO, older-mtime source with new content refreshes a newer-mtime dest."""
    src = tmp_path / "src"
    dst_xo = tmp_path / "dst_xo"
    dst_force = tmp_path / "dst_force"
    src.mkdir()
    dst_xo.mkdir()
    dst_force.mkdir()
    stale = "PRE6120 no opencode\n"
    fresh = "FR6154 opencode fuel helper\n"
    # Dest files first with newer content stamp, then age the source file older.
    for d in (dst_xo, dst_force):
        (d / "Get-BobAgentFuel.ps1").write_text(stale, encoding="utf-8")
    time.sleep(1.05)
    (src / "Get-BobAgentFuel.ps1").write_text(fresh, encoding="utf-8")
    # Make dest mtimes newer than source (simulate flat compose newer than git checkout).
    now = time.time()
    os.utime(src / "Get-BobAgentFuel.ps1", (now - 120, now - 120))
    for d in (dst_xo, dst_force):
        os.utime(d / "Get-BobAgentFuel.ps1", (now - 5, now - 5))

    rc_xo = _robo(src, dst_xo, "/XO")
    rc_f = _robo(src, dst_force)
    assert rc_xo < 8 and rc_f < 8
    assert (dst_xo / "Get-BobAgentFuel.ps1").read_text(encoding="utf-8") == stale
    assert (dst_force / "Get-BobAgentFuel.ps1").read_text(encoding="utf-8") == fresh
