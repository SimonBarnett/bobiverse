"""FR #3900: upgrade from AircConsole / wrong ConsoleHome must keep or heal NickServ GUID."""
from __future__ import annotations

import os
from pathlib import Path

import airc_console_service as svc
from repo_layout import ROOT

INSTALL = ROOT / "airc" / "scripts" / "Install-Airc.ps1"
INSTALL_CONSOLE = ROOT / "airc" / "scripts" / "Install-AircConsole.ps1"
SERVICE = ROOT / "airc" / "scripts" / "airc_console_service.py"
SKILL = (
    ROOT
    / "airc"
    / ".grok"
    / "skills"
    / "bobiverse-airc-troubleshooting"
    / "SKILL.md"
)


def make(tmp_path, monkeypatch, extra=()):
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "x-server-pass")
    args = svc.build_arg_parser().parse_args(
        [
            "--machine",
            "flamingo",
            "--home",
            str(tmp_path),
            "--shop-mode",
            "registered",
            "--operators",
            "op",
            *extra,
        ]
    )
    s = svc.AircConsoleService(args)
    s.sent = []
    s.send = lambda line: s.sent.append(line)  # type: ignore[assignment]
    s.logs = []
    monkeypatch.setattr(svc, "info", lambda m: s.logs.append(m))
    return s


def test_fr3900_install_reads_legacy_aircconsole_appparameters():
    text = INSTALL.read_text(encoding="utf-8-sig")
    assert "FR #3900" in text
    assert "AircConsole" in text
    assert text.index("ServiceName 'Airc'") < text.index("ServiceName 'AircConsole'")
    assert "migrated console.password" in text
    console = INSTALL_CONSOLE.read_text(encoding="utf-8-sig")
    assert "FR #3900" in console
    assert "preserving identity from legacy AircConsole" in console


def test_fr3900_sasl_904_heals_from_legacy_password(tmp_path, monkeypatch):
    wrong = "11111111-1111-1111-1111-111111111111"
    right = "22222222-2222-2222-2222-222222222222"
    (tmp_path / "console.password").write_text(wrong + "\n", encoding="utf-8")
    legacy = tmp_path / "legacy_admin_airc"
    legacy.mkdir()
    (legacy / "console.password").write_text(right + "\n", encoding="utf-8")

    # Point legacy scanner at our fixture dir via USERPROFILE\.airc BEFORE service init
    # is not required — heal reads env at 904 time.
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "profile"))
    profile_airc = Path(os.environ["USERPROFILE"]) / ".airc"
    profile_airc.mkdir(parents=True)
    (profile_airc / "console.password").write_text(right + "\n", encoding="utf-8")

    s = make(tmp_path, monkeypatch)
    assert s.nickserv_password == wrong
    s.on_line(":srv 904 * :SASL authentication failed")
    assert s.nickserv_password == right
    assert (tmp_path / "console.password").read_text(encoding="utf-8").strip() == right
    assert any("FR #3900 healed" in m for m in s.logs), s.logs
    assert s._force_reconnect is True
    # Only one heal attempt even if 904 repeats.
    s._force_reconnect = False
    s.on_line(":srv 904 * :SASL authentication failed")
    assert s._force_reconnect is False


def test_fr3900_sasl_904_without_legacy_keeps_error(tmp_path, monkeypatch):
    (tmp_path / "console.password").write_text(
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n", encoding="utf-8"
    )
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "empty_profile"))
    Path(os.environ["USERPROFILE"]).mkdir(parents=True)
    s = make(tmp_path, monkeypatch)
    s.on_line(":srv 904 * :SASL authentication failed")
    assert any("SASL failed (904)" in m and "SAPASSWD" in m for m in s.logs), s.logs
    assert s._force_reconnect is False


def test_fr3900_skill_documents_aircconsole_upgrade():
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3900" in skill
    assert "AircConsole" in skill
    assert "SAPASSWD" in skill
    text = SERVICE.read_text(encoding="utf-8")
    assert "_try_heal_console_password_from_legacy" in text
    assert "FR #3900" in text
