"""FR #1316: BobCallback must run as the digest-home owner (not SYSTEM vs Admin .bobiverse)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

import bobcallback
from repo_layout import ROOT

JEEVES = Path(__file__).resolve().parents[1]
INSTALL = JEEVES / "scripts" / "Install-Jeeves.ps1"
REGISTER = JEEVES / "scripts" / "Register-BobCallbackTask.ps1"
START = JEEVES / "scripts" / "Start-Jeeves.ps1"
WEBHOOKS_DOC = JEEVES / "docs" / "webhooks.md"


def test_assert_home_usable_ok(tmp_path, capsys):
    bobcallback.assert_home_usable(tmp_path)
    out = capsys.readouterr().out
    assert "INFO principal user=" in out
    assert f"home={tmp_path}" in out or str(tmp_path) in out
    leftovers = list(tmp_path.glob(".bobcallback-write-probe.*"))
    assert leftovers == []


def test_assert_home_usable_refuses_unwritable(tmp_path, monkeypatch):
    home = tmp_path / "locked"
    home.mkdir()

    def boom(*_a, **_k):
        raise OSError(13, "Access is denied")

    monkeypatch.setattr(Path, "write_text", boom)
    with pytest.raises(SystemExit) as ei:
        bobcallback.assert_home_usable(home)
    assert ei.value.code == 2


def test_install_jeeves_does_not_register_bobcallback_as_system():
    text = INSTALL.read_text(encoding="utf-8-sig")
    assert "Register-BobCallbackTask.ps1" in text
    assert "FR #1316" in text
    # Must not recreate the cross-principal wedge.
    assert "/RU SYSTEM" not in text
    assert "never SYSTEM against Admin home" in text or "not SYSTEM" in text


def test_register_bobcallback_task_script_uses_interactive_home_owner():
    assert REGISTER.is_file()
    text = REGISTER.read_text(encoding="utf-8-sig")
    assert not REGISTER.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "LogonType Interactive" in text or "-LogonType Interactive" in text
    assert "FR #1316" in text
    assert "New-ScheduledTaskPrincipal" in text
    # Must not actually schtasks-register as SYSTEM (comment mention of the anti-pattern is ok).
    assert "schtasks" not in text.lower() or "/RU SYSTEM" not in text
    assert "-UserId" in text and "Interactive" in text


def test_start_jeeves_detects_running_without_listen_wedge():
    text = START.read_text(encoding="utf-8-sig")
    assert "FR #1316" in text
    assert "wedge" in text.lower()
    assert "user-context" in text.lower() or "Start-Process" in text
    assert "Running but" in text or "not LISTENING" in text


def test_webhooks_doc_notes_principal_must_match_home():
    text = WEBHOOKS_DOC.read_text(encoding="utf-8")
    assert not WEBHOOKS_DOC.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "FR #1316" in text
    assert "SYSTEM" in text
    assert "Register-BobCallbackTask" in text or "home owner" in text.lower()


def test_legacy_root_resolves_register_script():
    p = ROOT / "scripts" / "Register-BobCallbackTask.ps1"
    assert p.is_file(), p
