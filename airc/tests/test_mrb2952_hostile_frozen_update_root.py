"""Hostile pins for MRB #2952 / FR #2949 frozen UPDATE install root.

Product on main via #2952. Pins troubleshooting row + helpers + product tests.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TROUBLE = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-troubleshooting" / "SKILL.md"
CONSOLE = ROOT / "airc" / "scripts" / "airc_console.py"
SERVICE = ROOT / "airc" / "scripts" / "airc_console_service.py"
PRODUCT_TEST = ROOT / "airc" / "tests" / "test_fr2949_frozen_update_install_root.py"


def test_mrb2952_troubleshooting_pin_fr2949():
    text = TROUBLE.read_text(encoding="utf-8")
    assert text.endswith("\n"), TROUBLE.name
    assert not text.startswith("\ufeff"), TROUBLE.name
    assert "2949" in text
    assert "updater-missing" in text
    assert "_MEI" in text
    assert "resolve_fleet_update_install_root" in text
    assert "resolve_airc_install_root" in text
    assert "never shell fallthrough" in text or "action=update" in text


def test_mrb2952_code_pins_fleet_update_root():
    console = CONSOLE.read_text(encoding="utf-8")
    assert "def resolve_fleet_update_install_root" in console
    assert "FR #2949" in console or "2949" in console
    service = SERVICE.read_text(encoding="utf-8")
    assert "resolve_airc_install_root()" in service
    assert "install_root = str(Path(__file__).resolve().parents[1])" not in service
    assert "FR #77 / #2949" in service or "#2949" in service


def test_mrb2952_product_test_module_present():
    assert PRODUCT_TEST.is_file(), PRODUCT_TEST
    text = PRODUCT_TEST.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert not text.startswith("\ufeff")
    assert "test_fr2949_schedule_finds_updater_under_install_root_scripts" in text
    assert "test_fr2949_schedule_frozen_re_resolves_when_install_root_is_mei" in text
    assert "test_fr2949_update_missing_still_action_update_not_shell" in text
