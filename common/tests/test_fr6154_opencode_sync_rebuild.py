"""FR #6154: Sync/ff + pack path ships OpenCode fuel helpers and worker markers.

Live installs can keep a pre-#6120 Get-BobAgentFuel.ps1 when Sync robocopy uses /XO
on tools/ (git checkout mtimes older than the flat copy). Pack/Sync must force tray
tools (same bar as FR #269 scripts) and include bob-setup-opencode + opencode markers.
"""
from __future__ import annotations

from pathlib import Path

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


def test_fr6154_sync_tray_tools_mirror_forced_no_xo():
    """Tray tools robocopy must not use /XO (FR #269 class) so OpenCode fuel helpers refresh."""
    text = _sync()
    assert "FR #6154" in text
    assert "tools-no-xo" in text.lower()
    assert "third_party\\bob-tray\\tools" in text
    assert "Dst -eq 'tools'" in text


def test_fr6154_sync_includes_bob_setup_opencode_skill():
    text = _sync()
    assert "bob-setup-opencode" in text


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
    assert "third_party\\bob-tray" in pack or "bob\\tray" in pack
    build = BUILD.read_text(encoding="utf-8-sig")
    assert "--dry-run" in build
    assert "bob_worker.py" in build


def test_fr6154_pre6120_marker_absent_means_fail_probe():
    """Build smoke requires decision JSON; rebuilt exe must embed OpenCode selection (Pack)."""
    build = BUILD.read_text(encoding="utf-8-sig")
    assert '"decision"' in build or "'decision'" in build