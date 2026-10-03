"""FR #836: tray Private defaults/messages must not quote archived repo full names."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRAY_PRIVATE = ROOT / "bob" / "tray" / "src" / "Private"
AGENTWATCHER = ROOT / "bob" / "agentwatcher"

ARCHIVED_QUOTED = (
    "'SimonBarnett/agentic_build'",
    '"SimonBarnett/agentic_build"',
    "'SimonBarnett/AgentMonitor'",
    '"SimonBarnett/AgentMonitor"',
    "'SimonBarnett/gh-Jeeves'",
    '"SimonBarnett/gh-Jeeves"',
    "'SimonBarnett/agentic_irc'",
    '"SimonBarnett/agentic_irc"',
)

# Live defaults the FR asks for.
LIVE = "SimonBarnett/bobiverse"

TARGET_FILES = (
    TRAY_PRIVATE / "Get-BobGh.ps1",
    TRAY_PRIVATE / "Report-BobDeterministicException.ps1",
    TRAY_PRIVATE / "Copy-BobProjectSkills.ps1",
    TRAY_PRIVATE / "Invoke-Grok.ps1",
    TRAY_PRIVATE / "Start-BobRepoPairWorker.ps1",
    AGENTWATCHER / "Watch-AgentHealth.ps1",
    AGENTWATCHER / "README.md",
)


def test_target_files_exist():
    for path in TARGET_FILES:
        assert path.is_file(), path


def test_no_quoted_archived_full_name_defaults():
    for path in TARGET_FILES:
        text = path.read_text(encoding="utf-8-sig")
        for needle in ARCHIVED_QUOTED:
            assert needle not in text, f"{path.name} still quotes {needle}"


def test_get_bob_gh_defaults_to_bobiverse():
    text = (TRAY_PRIVATE / "Get-BobGh.ps1").read_text(encoding="utf-8-sig")
    assert "return 'SimonBarnett/bobiverse'" in text or 'return "SimonBarnett/bobiverse"' in text


def test_exception_owning_repo_defaults_to_bobiverse():
    text = (TRAY_PRIVATE / "Report-BobDeterministicException.ps1").read_text(encoding="utf-8-sig")
    assert "return 'SimonBarnett/bobiverse'" in text
    # No archived return targets remain.
    for repo in ("AgentMonitor", "agentic_irc", "gh-Jeeves", "agentic_build"):
        assert not re.search(rf"return\s+'SimonBarnett/{repo}'", text), repo


def test_skill_hint_checks_match_bobiverse():
    for name in ("Invoke-Grok.ps1", "Start-BobRepoPairWorker.ps1"):
        text = (TRAY_PRIVATE / name).read_text(encoding="utf-8-sig")
        assert "SimonBarnett/bobiverse" in text
        assert "SimonBarnett/agentic_build" not in text


def test_agentwatcher_readme_points_at_bobiverse():
    text = (AGENTWATCHER / "README.md").read_text(encoding="utf-8-sig")
    assert "SimonBarnett/bobiverse" in text
    assert "SimonBarnett/AgentMonitor" not in text

def test_fleet_peek_legacy_leaf_maps_to_bobiverse():
    text = (TRAY_PRIVATE / "Get-BobFleetPeek.ps1").read_text(encoding="utf-8-sig")
    assert "return 'SimonBarnett/bobiverse'" in text
    assert "return 'SimonBarnett/agentic_build'" not in text
    assert "return 'SimonBarnett/agentic_irc'" not in text
