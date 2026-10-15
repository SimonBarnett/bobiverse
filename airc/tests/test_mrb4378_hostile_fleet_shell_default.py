"""MRB #4378 hostile pins for FR #4030 fleet fresh shell=operators (1.0.0)."""
from __future__ import annotations

import airc_console as ac
from repo_layout import ROOT

INSTALL = ROOT / "airc" / "scripts" / "Install-Airc.ps1"
SKILL = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc" / "SKILL.md"


def test_mrb4378_fleet_fresh_operators_not_off():
    assert (
        ac.resolve_shell_mode_for_install(
            prior_shell=None, explicit=None, had_prior_service=False, is_bob_machine=False
        )
        == "operators"
    )


def test_mrb4378_legacy_fresh_default_off_migrates_without_bob():
    assert (
        ac.resolve_shell_mode_for_install(
            prior_shell="off",
            explicit=None,
            had_prior_service=True,
            is_bob_machine=False,
            prior_shell_source="fresh-default",
        )
        == "operators"
    )


def test_mrb4378_explicit_off_stays_off_fleet_and_bob():
    assert (
        ac.resolve_shell_mode_for_install(
            prior_shell="off",
            explicit=None,
            had_prior_service=True,
            is_bob_machine=False,
            prior_shell_source="explicit",
        )
        == "off"
    )
    assert (
        ac.resolve_shell_mode_for_install(
            prior_shell="off",
            explicit="off",
            had_prior_service=False,
            is_bob_machine=True,
        )
        == "off"
    )


def test_mrb4378_workstation_still_defaults_off():
    assert (
        ac.resolve_shell_mode_for_install(
            prior_shell=None,
            explicit=None,
            had_prior_service=False,
            profile="workstation",
            is_bob_machine=False,
        )
        == "off"
    )


def test_mrb4378_install_ps1_and_skill_contiguous():
    inst = INSTALL.read_text(encoding="utf-8-sig")
    assert "legacy fleet fresh-default" in inst
    assert "1.0.0: fleet fresh default operators" in inst
    # Fresh else-branch operators (not off).
    assert "$resolvedShell = 'operators'" in inst
    assert "$resolvedShell = 'off'" in inst  # workstation / explicit still present
    skill = SKILL.read_text(encoding="utf-8")
    assert "Fleet fresh default `shell=operators`" in skill or "fleet fresh default" in skill.lower()
    assert "Fresh default `shell=off`" not in skill
