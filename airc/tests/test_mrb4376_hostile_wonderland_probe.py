"""MRB #4376 hostile behavioral pins for FR #3834 / 1.0.0 wonderland regression."""
from __future__ import annotations

import airc_console_service as svc
from repo_layout import ROOT

INSTALL = ROOT / "airc" / "scripts" / "Install-AircConsole.ps1"
START = ROOT / "airc" / "scripts" / "Start-AircConsole.ps1"
SERVICE = ROOT / "airc" / "scripts" / "airc_console_service.py"


def make(tmp_path, monkeypatch, *, shop_mode="auto", nick=None, machine="walrus"):
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "x-server-pass")
    extra = ["--shop-mode", shop_mode]
    if nick:
        extra.extend(["--nick", nick])
    args = svc.build_arg_parser().parse_args(
        [
            "--machine",
            machine,
            "--home",
            str(tmp_path),
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


def test_mrb4376_auto_plus_explicit_nick_starts_on_wonderland(tmp_path, monkeypatch):
    s = make(tmp_path, monkeypatch, shop_mode="auto", nick="walrus_console")
    assert s._nick_explicit is True
    assert s.channel == "#wonderland"
    assert s.shop_channel == "#walrus"


def test_mrb4376_auto_plus_explicit_nick_001_probes_not_force_registered(tmp_path, monkeypatch):
    s = make(tmp_path, monkeypatch, shop_mode="auto", nick="walrus_console")
    s.on_line(":irc.example 001 walrus_console :Welcome")
    assert s._probe_state == "waiting"
    assert any(l.startswith("PRIVMSG ChanServ :INFO #walrus") for l in s.sent), s.sent
    assert s.channel == "#wonderland"
    # Must not have JOINed #walrus before probe settles.
    assert not any(l.upper().startswith("JOIN #walrus") for l in s.sent), s.sent


def test_mrb4376_forced_registered_still_joins_shop(tmp_path, monkeypatch):
    s = make(tmp_path, monkeypatch, shop_mode="registered")
    assert s.channel == "#walrus"
    s.on_line(":irc.example 001 walrus_console :Welcome")
    assert s._active_mode == "registered"
    assert any("JOIN" in l.upper() and "#walrus" in l for l in s.sent) or s.channel == "#walrus"


def test_mrb4376_install_bakes_shop_mode_auto_and_wonderland_info():
    inst = INSTALL.read_text(encoding="utf-8-sig")
    start = START.read_text(encoding="utf-8-sig")
    assert "--shop-mode auto" in inst
    assert "-ShopMode auto" in inst
    assert "else #wonderland" in inst
    assert "console will JOIN #" not in inst
    assert "else #wonderland" in start
    assert "fleet shop #" not in start
    # Contiguous with FR #3900 prefer-prior (same Install-AircConsole after main merge).
    assert "prefer prior console.password" in inst or "password-minted" in inst


def test_mrb4376_001_block_has_no_nick_explicit_short_circuit():
    t = SERVICE.read_text(encoding="utf-8")
    block = t.split('if cmd == "001":', 1)[1].split('if cmd == "433":', 1)[0]
    assert "_nick_explicit" not in block
    assert "_start_chanserv_probe" in block
