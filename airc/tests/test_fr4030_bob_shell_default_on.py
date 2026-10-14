"""FR #4030: airc remote shell defaults ON (operators) on Bob machines."""
from __future__ import annotations

from pathlib import Path

import airc_console as ac
from repo_layout import ROOT

INSTALL = (ROOT / "airc" / "scripts" / "Install-Airc.ps1").read_text(encoding="utf-8-sig")
SKILL = (ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc" / "SKILL.md").read_text(encoding="utf-8")
OPS = (ROOT / "airc" / "docs" / "airc-ops.md").read_text(encoding="utf-8-sig")


def test_fr4030_bob_machine_fresh_defaults_operators():
    assert (
        ac.resolve_shell_mode_for_install(
            prior_shell=None,
            explicit=None,
            had_prior_service=False,
            is_bob_machine=True,
        )
        == "operators"
    )


def test_fr4030_bob_machine_migrates_legacy_fresh_off():
    # flamingo class: prior off without explicit source -> operators
    assert (
        ac.resolve_shell_mode_for_install(
            prior_shell="off",
            explicit=None,
            had_prior_service=True,
            is_bob_machine=True,
            prior_shell_source=None,
        )
        == "operators"
    )
    assert (
        ac.resolve_shell_mode_for_install(
            prior_shell="off",
            explicit=None,
            had_prior_service=True,
            is_bob_machine=True,
            prior_shell_source="fresh-default",
        )
        == "operators"
    )


def test_fr4030_bob_machine_honours_explicit_off():
    assert (
        ac.resolve_shell_mode_for_install(
            prior_shell="operators",
            explicit="off",
            had_prior_service=True,
            is_bob_machine=True,
        )
        == "off"
    )
    assert (
        ac.resolve_shell_mode_for_install(
            prior_shell="off",
            explicit=None,
            had_prior_service=True,
            is_bob_machine=True,
            prior_shell_source="explicit",
            prior_shell_explicit=True,
        )
        == "off"
    )


def test_fr4030_non_bob_fresh_still_off():
    assert (
        ac.resolve_shell_mode_for_install(
            prior_shell=None,
            explicit=None,
            had_prior_service=False,
            is_bob_machine=False,
        )
        == "off"
    )


def test_fr4030_detect_bob_machine(tmp_path: Path):
    airc_root = tmp_path / "airc"
    bob_root = tmp_path / "bob"
    airc_root.mkdir()
    assert ac.detect_bob_machine(install_root=airc_root) is False
    bob_root.mkdir()
    (bob_root / "VERSION").write_text("0.1.0\n", encoding="utf-8")
    assert ac.detect_bob_machine(install_root=airc_root) is True


def test_fr4030_warn_shell_off_on_bob():
    line = ac.warn_shell_off_on_bob_line(
        shell_mode="off",
        is_bob_machine=True,
        shell_source="explicit",
        profile="fleet",
    )
    assert line.startswith("WARN")
    assert "shell=off" in line
    assert "explicit" in line
    assert (
        ac.warn_shell_off_on_bob_line(
            shell_mode="operators",
            is_bob_machine=True,
            shell_source="bob-default",
            profile="fleet",
        )
        is None
    )


def test_fr4030_install_ps1_wires_bob_default_and_source():
    assert "FR #4030" in INSTALL
    assert "bob-default" in INSTALL or "shell_source" in INSTALL
    assert "migrated" in INSTALL.lower() or "shell_source" in INSTALL
    # fresh fleet on Bob must not hard-default off after Bob branch
    assert "isBobMachine" in INSTALL or "BobMachine" in INSTALL or "ircBob" in INSTALL


def test_fr4030_docs_skill():
    assert "FR #4030" in SKILL or "FR #4030" in OPS
    assert "Bob" in SKILL or "bob machine" in SKILL.lower() or "ircBob" in OPS