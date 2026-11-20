"""FR #8412: auto-select dialog uses resolve_opencode_cmd, not a false missing."""

from __future__ import annotations

from pathlib import Path

import bob.scripts.bob_worker as bw


def test_programs_opencode_is_offered_when_winget_links_absent(tmp_path, monkeypatch):
    local = tmp_path / "Local"
    exe = local / "Programs" / "opencode" / "opencode.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.delenv("BOB_OPENCODE_EXE", raising=False)
    monkeypatch.delenv("BOB_OPENCODE_SEAT_HOME", raising=False)
    monkeypatch.delenv("BOB_GROK_WEEKLY_USER_HOME", raising=False)
    reasons: list = []
    found = bw.resolve_opencode_cmd(which=lambda _name: None, reasons=reasons)
    assert found == str(exe)
    fuel = bw.Fuel(0, 0, 0, "exhausted", opencode_go=40)
    dec = bw.select_agent(fuel, None, r"C:\g\agent.exe", found)
    assert dec.kind == "opencode"
    assert "opencode.exe missing" not in dec.reason


def test_choose_logs_missing_only_when_resolve_fails(tmp_path, monkeypatch):
    local = tmp_path / "Local"
    exe = local / "Programs" / "opencode" / "opencode.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.delenv("BOB_OPENCODE_EXE", raising=False)
    monkeypatch.setattr(bw, "resolve_cursor_cmd", lambda: None)
    monkeypatch.setattr(bw, "resolve_grok_exe", lambda: r"C:\g\agent.exe")
    monkeypatch.setattr(bw, "read_fuel", lambda _root: bw.Fuel(0, 0, 0, "exhausted", opencode_go=40))
    monkeypatch.setattr(bw, "preflight_xai_signin", lambda: "ok")
    logs: list = []

    class _Args:
        install_root = str(tmp_path)

    dec, _cursor, _grok, _fuel, _ok, _signin = bw._choose(_Args(), logs.append, tmp_path, "agent")
    text = "\n".join(logs)
    assert dec.kind == "opencode"
    assert "opencode.exe missing" not in text
    assert "opencode.exe missing" not in dec.reason
