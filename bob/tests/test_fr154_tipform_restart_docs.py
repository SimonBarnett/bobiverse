"""FR #154: TipForm Restart docs match Start-BobFleetTray -ForceNew; Restart-BobEar stays ear-only."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

WATCH = ROOT / "bob" / "third_party" / "bob-tray" / "tools" / "Watch-BobTray.ps1"
START = ROOT / "bob" / "third_party" / "bob-tray" / "tools" / "Start-BobFleetTray.ps1"
EAR = ROOT / "bob" / "scripts" / "Restart-BobEar.ps1"

DOC_PATHS = [
    ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob" / "SKILL.md",
    ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-commands" / "SKILL.md",
    ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-troubleshooting" / "SKILL.md",
    ROOT / "bob" / "docs" / "bob-ear.md",
    ROOT / "common" / "docs" / "post-install.md",
]


def test_live_tray_restart_uses_forcenew_not_restart_bob_ear_directly():
    watch = WATCH.read_text(encoding="utf-8", errors="replace")
    start = START.read_text(encoding="utf-8", errors="replace")
    assert "function Restart-BobTrayWatcher" in watch
    assert "Start-BobFleetTray" in watch and "-ForceNew" in watch
    assert "Restart-BobEar.ps1" not in watch.split("function Restart-BobTrayWatcher", 1)[1][:800]
    assert "Restart-BobTrayService" in start
    assert EAR.is_file()


def test_skills_and_docs_name_forcenew_path_and_ear_only_shortcut():
    for path in DOC_PATHS:
        text = path.read_text(encoding="utf-8", errors="replace")
        assert "Start-BobFleetTray -ForceNew" in text or "Start-BobFleetTray `-ForceNew" in text, path
        assert "Restart-BobEar" in text, path
        # old TipForm phrasing must not claim Restart-BobEar is the TipForm menu handler
        assert "TipForm **Restart ircBob**" not in text, path
        assert "TipForm **Restart ircBob** calls `Restart-BobEar`" not in text, path
