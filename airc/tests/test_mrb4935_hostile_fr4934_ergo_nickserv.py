"""docs/mrb-4935 hostile pins for FR #4934 / PR #4935.

Ergo NickServ success must write console.nickserv-ok under --home and clear mint.
"""
from __future__ import annotations

from pathlib import Path

import airc_console_service as svc
from repo_layout import ROOT

SERVICE = ROOT / "airc" / "scripts" / "airc_console_service.py"
INSTALL_AIRC = ROOT / "airc" / "scripts" / "Install-Airc.ps1"
INSTALL_CONSOLE = ROOT / "airc" / "scripts" / "Install-AircConsole.ps1"


def make(tmp_path, monkeypatch):
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
        ]
    )
    s = svc.AircConsoleService(args)
    s.sent = []
    s.send = lambda line: s.sent.append(line)  # type: ignore[assignment]
    return s


def test_mrb4935_mark_nickserv_ok_clears_mint_and_stays_under_home(tmp_path, monkeypatch):
    (tmp_path / "console.password").write_text(
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n", encoding="utf-8"
    )
    (tmp_path / "console.password-minted").write_text("install\n", encoding="ascii")
    s = make(tmp_path, monkeypatch)
    s._mark_nickserv_ok("hostile-pin")
    assert (tmp_path / "console.nickserv-ok").is_file()
    assert "hostile-pin" in (tmp_path / "console.nickserv-ok").read_text(encoding="ascii")
    assert not (tmp_path / "console.password-minted").is_file()


def test_mrb4935_bare_you_are_now_logged_in_without_apostrophe_still_marks(
    tmp_path, monkeypatch
):
    """Keep Atheme-style 'you are now logged in' while Ergo uses you're."""
    (tmp_path / "console.password").write_text(
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n", encoding="utf-8"
    )
    s = make(tmp_path, monkeypatch)
    s.on_line(
        ":NickServ!ns@services NOTICE walrus_console :You are now logged in as walrus_console"
    )
    assert (tmp_path / "console.nickserv-ok").is_file()


def test_mrb4935_source_pins_installers_refuse_overwrite_with_nickserv_ok():
    airc = INSTALL_AIRC.read_text(encoding="utf-8")
    console = INSTALL_CONSOLE.read_text(encoding="utf-8")
    svc_txt = SERVICE.read_text(encoding="utf-8")
    assert "hasNickservOk" in airc or "nickserv-ok" in airc
    assert "hasNickservOk" in console or "nickserv-ok" in console
    assert "FR #4934" in airc and "FR #4934" in console
    assert "account created" in svc_txt
    assert "you're now logged in" in svc_txt
    assert 'cmd == "900"' in svc_txt or '"900"' in svc_txt
