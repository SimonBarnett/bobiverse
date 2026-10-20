"""FR #4934: write console.nickserv-ok on Ergo NickServ text / 900; clear mint marker.

Ergo sends 'Account created' and 'You're now logged in as X' --- not Atheme
'is now registered'. Fresh installs skipped SASL (mint marker) so only NOTICE
could write the marker; mismatched phrases left mint forever and the next
install/start minted a new GUID.
"""
from __future__ import annotations

from pathlib import Path

import airc_console_service as svc
from repo_layout import ROOT

SERVICE = ROOT / "airc" / "scripts" / "airc_console_service.py"
INSTALL_AIRC = ROOT / "airc" / "scripts" / "Install-Airc.ps1"
INSTALL_CONSOLE = ROOT / "airc" / "scripts" / "Install-AircConsole.ps1"
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
            "walrus",
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


def test_fr4934_ergo_account_created_writes_marker_and_clears_mint(tmp_path, monkeypatch):
    (tmp_path / "console.password").write_text(
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n", encoding="utf-8"
    )
    (tmp_path / "console.password-minted").write_text("install\n", encoding="ascii")
    s = make(tmp_path, monkeypatch)
    s.on_line(":NickServ!ns@services NOTICE walrus_console :Account created")
    marker = tmp_path / "console.nickserv-ok"
    assert marker.is_file()
    assert "nickserv-notice" in marker.read_text(encoding="ascii")
    assert not (tmp_path / "console.password-minted").is_file()


def test_fr4934_ergo_youre_now_logged_in_writes_marker(tmp_path, monkeypatch):
    (tmp_path / "console.password").write_text(
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n", encoding="utf-8"
    )
    (tmp_path / "console.password-minted").write_text("install\n", encoding="ascii")
    s = make(tmp_path, monkeypatch)
    s.on_line(
        ":NickServ!ns@services NOTICE walrus_console :"
        "You're now logged in as walrus_console"
    )
    marker = tmp_path / "console.nickserv-ok"
    assert marker.is_file()
    assert not (tmp_path / "console.password-minted").is_file()


def test_fr4934_account_already_exists_alone_does_not_mark(tmp_path, monkeypatch):
    """REGISTER reject without login must not write nickserv-ok (FR #4934)."""
    s = make(tmp_path, monkeypatch)
    s.on_line(":NickServ!ns@services NOTICE walrus_console :Account already exists")
    assert not (tmp_path / "console.nickserv-ok").is_file()


def test_fr4934_rpl_loggedin_900_writes_marker_and_clears_mint(tmp_path, monkeypatch):
    (tmp_path / "console.password").write_text(
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n", encoding="utf-8"
    )
    (tmp_path / "console.password-minted").write_text("install\n", encoding="ascii")
    s = make(tmp_path, monkeypatch)
    s.on_line(":srv 900 walrus_console walrus_console!u@h walrus_console :You are now logged in")
    marker = tmp_path / "console.nickserv-ok"
    assert marker.is_file()
    assert "rpl-loggedin-900" in marker.read_text(encoding="ascii")
    assert not (tmp_path / "console.password-minted").is_file()


def test_fr4934_sasl_903_backfills_missing_marker(tmp_path, monkeypatch):
    guid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    (tmp_path / "console.password").write_text(guid + "\n", encoding="utf-8")
    (tmp_path / "console.password-minted").write_text("install\n", encoding="ascii")
    assert not (tmp_path / "console.nickserv-ok").is_file()
    s = make(tmp_path, monkeypatch)
    before = (tmp_path / "console.password").read_text(encoding="utf-8")
    s.on_line(":srv 903 * :SASL authentication successful")
    assert (tmp_path / "console.nickserv-ok").is_file()
    assert "sasl-903" in (tmp_path / "console.nickserv-ok").read_text(encoding="ascii")
    assert not (tmp_path / "console.password-minted").is_file()
    assert (tmp_path / "console.password").read_text(encoding="utf-8") == before


def test_fr4934_password_file_outside_home_marker_stays_in_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    pw = tmp_path / "config" / "ergo.password"
    pw.parent.mkdir()
    pw.write_text("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n", encoding="utf-8")
    s = make(home, monkeypatch, extra=["--password-file", str(pw)])
    s.on_line(":NickServ!ns@services NOTICE walrus_console :Account created")
    assert (home / "console.nickserv-ok").is_file()
    assert not (pw.parent / "console.nickserv-ok").is_file()
    assert pw.read_text(encoding="utf-8").startswith("aaaaaaaa-")


def test_fr4934_restart_with_marker_requests_sasl(tmp_path, monkeypatch):
    (tmp_path / "console.password").write_text(
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n", encoding="utf-8"
    )
    (tmp_path / "console.nickserv-ok").write_text("nickserv-notice\n", encoding="ascii")
    s = make(tmp_path, monkeypatch)
    s.handshake()
    assert any(l.startswith("CAP REQ :") and "sasl" in l for l in s.sent), s.sent
    assert (tmp_path / "console.password").read_text(encoding="utf-8").startswith("aaaaaaaa-")


def test_fr4934_source_pins_ergo_phrases_and_900():
    text = SERVICE.read_text(encoding="utf-8")
    assert "FR #4934" in text
    assert "account created" in text
    assert "you're now logged in" in text
    assert "rpl-loggedin-900" in text
    assert 'cmd == "900"' in text
    assert '"900"' in text  # routed in on_line SASL numeric set


def test_fr4934_installer_pins_nickserv_ok_guard():
    airc = INSTALL_AIRC.read_text(encoding="utf-8")
    console = INSTALL_CONSOLE.read_text(encoding="utf-8")
    assert "FR #4934" in airc
    assert "FR #4934" in console
    assert "nickserv-ok" in airc
    assert "nickserv-ok" in console
    assert "never replace console.password once nickserv-ok" in airc.lower() or (
        "hasNickservOk" in airc and "break" in airc
    )
    # ACL: SYSTEM (OI)(CI)F remains on ConsoleHome lockdown.
    assert "S-1-5-18" in console and "(OI)(CI)F" in console


def test_fr4934_skill_documents_ergo_and_marker_home():
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #4934" in skill
    assert "Account created" in skill or "account created" in skill.lower()
    assert "console.nickserv-ok" in skill
    assert "--password-file" in skill or "password-file" in skill
