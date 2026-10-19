"""FR #4388: walrus_console SASL 904 after upgrade must auto-recover without manual NickServ PASSWD.

#3900 heals when a *different* legacy console.password exists. On walrus (DC / LocalSystem)
the live home already holds the (wrong) GUID and no alternate file is found, so heal returns
False and the console loops on 433 forever. Tip must:

1. Expand legacy scan to LocalSystem / SystemProfile / ProgramData homes.
2. When heal finds nothing, one-shot OPER + NickServ PASSWD to set the existing
   {machine}_console account password to the local console.password, then reconnect.
"""
from __future__ import annotations

import os
from pathlib import Path

import airc_console_service as svc
from repo_layout import ROOT

SERVICE = ROOT / "airc" / "scripts" / "airc_console_service.py"
SKILL = (
    ROOT
    / "airc"
    / ".grok"
    / "skills"
    / "bobiverse-airc-troubleshooting"
    / "SKILL.md"
)
OPS = ROOT / "airc" / "docs" / "airc-ops.md"
POST = ROOT / "common" / "docs" / "post-install.md"


def make(tmp_path, monkeypatch, machine="walrus", extra=()):
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "x-server-pass")
    args = svc.build_arg_parser().parse_args(
        [
            "--machine",
            machine,
            "--home",
            str(tmp_path),
            "--shop-mode",
            "wonderland",
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


def test_fr4388_legacy_paths_include_systemprofile(tmp_path, monkeypatch):
    """LocalSystem MSI homes must be scanned (walrus DC path)."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "empty_profile"))
    Path(os.environ["USERPROFILE"]).mkdir(parents=True)
    (tmp_path / "console.password").write_text(
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n", encoding="utf-8"
    )
    s = make(tmp_path, monkeypatch)
    paths = [str(p).replace("\\", "/").lower() for p in s._legacy_console_password_paths()]
    joined = "\n".join(paths)
    assert "systemprofile" in joined or "system32/config/systemprofile" in joined, paths
    assert any(".airc/console.password" in p or ".airc\\console.password" in p.replace("/", "\\").lower() for p in paths) or any(
        p.endswith(".airc/console.password") for p in paths
    ), paths


def test_fr4388_sasl_904_heals_from_systemprofile(tmp_path, monkeypatch):
    wrong = "11111111-1111-1111-1111-111111111111"
    right = "22222222-2222-2222-2222-222222222222"
    (tmp_path / "console.password").write_text(wrong + "\n", encoding="utf-8")
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "empty_profile"))
    Path(os.environ["USERPROFILE"]).mkdir(parents=True)
    s = make(tmp_path, monkeypatch)
    sysprof = tmp_path / "sysprof_airc"
    sysprof.mkdir()
    (sysprof / "console.password").write_text(right + "\n", encoding="utf-8")
    # Inject SystemProfile candidate without requiring a real Windows path.
    monkeypatch.setattr(
        s,
        "_legacy_console_password_paths",
        lambda: [sysprof / "console.password"],
    )
    s.on_line(":srv 904 * :SASL authentication failed")
    assert s.nickserv_password == right
    assert (tmp_path / "console.password").read_text(encoding="utf-8").strip() == right
    assert any("FR #3900 healed" in m or "FR #4388 healed" in m for m in s.logs), s.logs
    assert s._force_reconnect is True


def test_fr4388_sasl_904_reclaims_via_oper_passwd(tmp_path, monkeypatch):
    """No legacy GUID -> OPER + NickServ PASSWD with local console.password, then reconnect."""
    guid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    (tmp_path / "console.password").write_text(guid + "\n", encoding="utf-8")
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "empty_profile"))
    Path(os.environ["USERPROFILE"]).mkdir(parents=True)
    s = make(tmp_path, monkeypatch)
    monkeypatch.setattr(s, "_legacy_console_password_paths", lambda: [])
    monkeypatch.setattr(
        s,
        "_load_oper_credentials_for_reclaim",
        lambda: ("admin", "FAKE_OPER_TOKEN_NOT_A_SECRET"),
    )
    s.on_line(":srv 904 * :SASL authentication failed")
    assert any(l.startswith("OPER admin ") for l in s.sent), s.sent
    assert any("FR #4388" in m and ("OPER" in m or "reclaim" in m.lower()) for m in s.logs), s.logs
    # CAP END so the connection can proceed to wait for 381.
    assert "CAP END" in s.sent
    # Simulate oper success -> PASSWD then reconnect.
    s.on_line(":srv 381 walrus_console :You are now an IRC operator")
    assert any(
        l.upper().startswith("PRIVMSG NICKSERV :PASSWD WALRUS_CONSOLE ")
        or l.upper().startswith("PRIVMSG NICKSERV :SAPASSWD WALRUS_CONSOLE ")
        for l in s.sent
    ), s.sent
    passwd_line = next(
        l
        for l in s.sent
        if "PASSWD" in l.upper() and "WALRUS_CONSOLE" in l.upper()
    )
    assert guid in passwd_line
    assert s._force_reconnect is True
    assert any("FR #4388" in m and ("PASSWD" in m or "reclaim" in m.lower()) for m in s.logs), s.logs
    # One-shot: second 904 must not re-OPER.
    s.sent.clear()
    s._force_reconnect = False
    s.on_line(":srv 904 * :SASL authentication failed")
    assert not any(l.startswith("OPER ") for l in s.sent), s.sent


def test_fr4388_sasl_904_without_oper_keeps_loud_error(tmp_path, monkeypatch):
    (tmp_path / "console.password").write_text(
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n", encoding="utf-8"
    )
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "empty_profile"))
    Path(os.environ["USERPROFILE"]).mkdir(parents=True)
    s = make(tmp_path, monkeypatch)
    monkeypatch.setattr(s, "_legacy_console_password_paths", lambda: [])
    monkeypatch.setattr(s, "_load_oper_credentials_for_reclaim", lambda: None)
    s.on_line(":srv 904 * :SASL authentication failed")
    assert any("SASL failed (904)" in m and "NickServ PASSWD" in m for m in s.logs), s.logs
    assert not any(l.startswith("OPER ") for l in s.sent), s.sent
    assert s._force_reconnect is False


def test_fr4388_oper_fail_491_falls_back_to_error(tmp_path, monkeypatch):
    guid = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
    (tmp_path / "console.password").write_text(guid + "\n", encoding="utf-8")
    s = make(tmp_path, monkeypatch)
    monkeypatch.setattr(s, "_legacy_console_password_paths", lambda: [])
    monkeypatch.setattr(
        s,
        "_load_oper_credentials_for_reclaim",
        lambda: ("admin", "FAKE_BAD_OPER"),
    )
    s.on_line(":srv 904 * :SASL authentication failed")
    assert any(l.startswith("OPER ") for l in s.sent), s.sent
    s.on_line(":srv 491 walrus_console :Password incorrect")
    assert any("FR #4388" in m and ("oper" in m.lower() or "491" in m) for m in s.logs), s.logs
    assert not any("PASSWD" in l.upper() for l in s.sent), s.sent


def test_fr4388_docs_and_skill_cover_auto_reclaim():
    text = SERVICE.read_text(encoding="utf-8")
    assert "FR #4388" in text
    assert "_load_oper_credentials_for_reclaim" in text
    assert "PASSWD" in text
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #4388" in skill
    ops = OPS.read_text(encoding="utf-8")
    assert "FR #4388" in ops
    post = POST.read_text(encoding="utf-8")
    assert "FR #4388" in post or "auto" in post.lower()
