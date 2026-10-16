"""FR #4390: confirm airc.json shell ON value is ``operators``, never the token ``shell``.

Walrus install test expected ``"shell": "shell"`` after #4030 migrated ``off`` ->
``operators``. That confuses the JSON *key* ``shell`` with a mode *value*. Valid
modes are only ``off`` | ``operators`` (FR #3287 / #4030). Migration writing
``operators`` with ``shell_source=migrated-from-fresh-off`` is correct.
"""
from __future__ import annotations

import airc_console as ac
from repo_layout import ROOT

INSTALL = ROOT / "airc" / "scripts" / "Install-Airc.ps1"
SKILL = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc" / "SKILL.md"
OPS = ROOT / "airc" / "docs" / "airc-ops.md"
POST = ROOT / "common" / "docs" / "post-install.md"


def test_fr4390_shell_mode_tokens_are_off_or_operators_only():
    assert ac.SHELL_MODE_TOKENS == frozenset({"off", "operators"})
    assert "shell" not in ac.SHELL_MODE_TOKENS


def test_fr4390_on_value_is_operators_never_literal_shell():
    """Bob / fleet ON after migrate-from-fresh-off is operators (not 'shell')."""
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
    assert (
        ac.resolve_shell_mode_for_install(
            prior_shell="off",
            explicit=None,
            had_prior_service=True,
            is_bob_machine=False,
            prior_shell_source=None,
        )
        == "operators"
    )
    # Literal "shell" is not a mode token (legacy --shell path fallthrough).
    mode, path = ac.normalize_shell_cli("shell")
    assert mode is None
    assert path == "shell"
    # Invalid prior "shell" does not become a third mode; fleet ON is operators.
    got = ac.resolve_shell_mode_for_install(
        prior_shell="shell",
        explicit=None,
        had_prior_service=True,
        is_bob_machine=True,
    )
    assert got == "operators"
    assert got != "shell"


def test_fr4390_install_migrates_to_operators_not_shell_token():
    text = INSTALL.read_text(encoding="utf-8-sig")
    assert "FR #4030" in text
    assert "migrated-from-fresh-off" in text
    assert "migrating shell=off -> operators" in text
    assert "$resolvedShell = 'operators'" in text
    # Must never mint the confused ON token "shell".
    assert "$resolvedShell = 'shell'" not in text
    assert 'shell = "shell"' not in text
    assert "shell=shell" not in text.replace("shell_source", "").replace("shell_explicit", "")


def test_fr4390_docs_pin_key_shell_value_operators():
    """Install/UAT checks must expect JSON key shell with value operators."""
    skill = SKILL.read_text(encoding="utf-8")
    ops = OPS.read_text(encoding="utf-8")
    post = POST.read_text(encoding="utf-8")
    blob = skill + "\n" + ops + "\n" + post
    assert "FR #4390" in blob
    assert "operators" in skill
    # Explicit anti-confusion line for external install tests.
    assert "never" in blob.lower() and (
        '"shell": "shell"' in blob or "value operators" in blob.lower() or "not the token" in blob.lower()
    )
