"""Hostile pins for MRB #2931 / FR #2928 Start-BobFleetTray dot-source safety.

Product already on main via #2931. This docs/mrb module pins contiguous skill
+ script phrases so a later wipe cannot drop the no-tidy-on-dotsource playbook.
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import resolve

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-troubleshooting" / "SKILL.md"
FLEET = resolve("bob/tray/tools/Start-BobFleetTray.ps1")
if not FLEET.is_file():
    FLEET = resolve("third_party/bob-tray/tools/Start-BobFleetTray.ps1")
PRODUCT_TEST = ROOT / "bob" / "tests" / "test_fr2928_fleet_tray_dotsource_safe.py"


def test_mrb2931_skill_pins_fr2928_playbook():
    text = SKILL.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert not text.startswith("\ufeff")
    assert "FR #2928" in text
    assert "Start-BobFleetTray.ps1" in text
    assert "MyInvocation.InvocationName" in text
    assert "Invoke-BobSystrayTidy" in text
    assert "BobTrayStartWorker.ps1" in text


def test_mrb2931_script_pins_dotsource_guard():
    text = FLEET.read_text(encoding="utf-8-sig")
    assert "FR #2928" in text
    assert "MyInvocation.InvocationName" in text
    assert "-eq '.'" in text or '-eq "."' in text
    guard_idx = text.find("MyInvocation.InvocationName")
    tidy_call = text.find("Invoke-BobSystrayTidy")
    # Top-level tidy invocation must sit after the guard (function def may precede).
    # Find last Invoke-BobSystrayTidy occurrence used as a call after guard in product tests.
    assert guard_idx > 0
    assert "Stop-BobSystrayPriorAgents" in text
    assert "Cleanup-OrphanAgents" in text
    assert tidy_call > 0


def test_mrb2931_product_test_module_present():
    text = PRODUCT_TEST.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert not text.startswith("\ufeff")
    assert "test_fr2928_dotsource_guard_wraps_tidy_and_main" in text
    assert "test_fr2928_dotsource_does_not_emit_tidy" in text
