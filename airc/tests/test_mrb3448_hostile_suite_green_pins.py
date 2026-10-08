"""Hostile pins for MRB #3448 / FR #3396: suite-green stale pin updates."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_mrb3448_fr2401_pin_uses_injectable_frozen_not_bare_call():
    text = _read("airc/tests/test_fr2401_airc_exe_self_update.py")
    assert "frozen = is_frozen_airc_exe() if _is_frozen is None else bool(_is_frozen)" in text
    assert "if not frozen:" in text
    # Must not re-require the pre-#3311 bare guard shape as the only gate.
    assert 'assert "if not is_frozen_airc_exe()" in text or "if not is_frozen_airc_exe():" in text' not in text


def test_mrb3448_mrb2363_remap_anchor_after_consolehome_new_item():
    text = _read("airc/tests/test_mrb2363_hostile_default_home.py")
    assert 't.index("New-Item -ItemType Directory -Force -Path $ConsoleHome")' in text
    assert 't.index("FR #2355 / #3288: remap user-profile homes")' in text
    assert "Resolve-AircSafeConsoleHome" in text


def test_mrb3448_plan_skill_keeps_how_to_plan_and_fleet_tooling_repo():
    text = _read("bob/.grok/skills/bobiverse-bob-plan/SKILL.md")
    assert "Harvest how-to-plan only" in text
    assert "bobiverse#3097" in text
    assert "`-Repo SimonBarnett/bobiverse`" in text
    assert "bob-worker/tray/fleet tooling" in text
    # Must not restore product-decisions-as-harvest routing.
    assert "product decisions → `-Repo SimonBarnett/<product>`" not in text
    assert "(use `-Repo SimonBarnett/<product>` for product decisions)" not in text


def test_mrb3448_unregister_autofocus_discovers_ai_root():
    text = _read("common/scripts/Unregister-BobAutoFocus.ps1")
    assert "Get-BobiverseAiRoot" in text
    assert "FR #3396: never hard-code C:\\ai" in text
