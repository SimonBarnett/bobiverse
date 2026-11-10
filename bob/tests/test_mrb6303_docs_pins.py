"""Hostile docs/mrb-6303 pins for FR #6301 tray fuel + agent starts."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
TRAY = ROOT / "tray" / "dialogs" / "BobTray.cs"
DOCS = ROOT / "docs" / "bob-tray-dialogs.md"
KEYS = ROOT.parents[0] / "common" / "tests" / "test_fr6301_opencode_keys.py"


def test_mrb6303_docs_describe_percent_left_and_digest_only():
    text = DOCS.read_text(encoding="utf-8")
    assert "FR #6301 tray fuel rows" in text
    assert "% left" in text
    assert "opencode-fuel.json" in text
    assert "no key set" in text
    assert "BOB_OPENCODE_MODEL" in text
    assert "#6309" in text or "follow-up" in text.lower()


def test_mrb6303_hover_paint_ignores_local_opencode_fuel_json():
    src = HOVER.read_text(encoding="utf-8-sig")
    paint_idx = src.find("function Get-BobTrayHover")
    assert paint_idx > 0
    paint = src[paint_idx:]
    assert "Read-BobOpencodeLocalFuel" not in paint
    assert "Format-BobOpencodeWindowLine" in src
    assert "% left" in src


def test_mrb6303_agent_starts_have_no_fuel_text_and_opencode_submenu():
    """FR #6301: no fuel text on starts. FR #6429: OpenCode is free/paid submenu."""
    tray = TRAY.read_text(encoding="utf-8")
    seed = tray[tray.index("void SeedAgentChoices") : tray.index("void SeedAgentChoices") + 900]
    assert "fuel unknown" not in seed
    assert 'AddAgentChoice(parent, "grok", "Grok"' in seed
    assert "AddOpencodeModelSubmenu" in seed
    assert 'AddAgentChoice(parent, "opencode", "OpenCode"' not in seed
    apply = tray[tray.index("void ApplyAgentList") : tray.index("void ApplyAgentList") + 2500]
    assert "Default model" not in apply
    assert "AddOpencodeModelSubmenu" in apply
    click = tray[tray.index("void OnAgentChoiceClick") : tray.index("void OnAgentChoiceClick") + 1200]
    assert "SetEnvironmentVariable(\"BOB_OPENCODE_MODEL\"" not in click
    docs = DOCS.read_text(encoding="utf-8")
    assert "FR #6429" in docs
    assert "Start free model" in docs
    assert "Start paid model" in docs


def test_mrb6303_part_d_key_tests_exist():
    assert KEYS.is_file()
    text = KEYS.read_text(encoding="utf-8")
    assert "no key set" in text
    assert "labelled" in text.lower()
    assert "SYSTEM" in text
