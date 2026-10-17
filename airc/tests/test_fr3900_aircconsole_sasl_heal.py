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
    # Isolate from the host Admin\\.airc GUID (fleet boxes often have one).
    monkeypatch.setattr(s, "_legacy_console_password_paths", lambda: [])
    # FR #4388: isolate from host oper.cred / ergo-oper discovery (reclaim would OPER).
    monkeypatch.setattr(s, "_load_oper_credentials_for_reclaim", lambda: None)
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


def test_fr3900_v1_install_prefers_prior_password_over_wrong_mint():
    """1.0.0 release-blocker: wrong mint in install\\home must lose to prior PasswordFile.

    Migrate-when-empty alone is not enough — MSI/LocalSystem can mint into
    InstallRoot\\home while the live GUID still lives under Admin\\.airc or the
    path recorded in airc-install.json. Prefer that prior file (overwrite dest)
    before Initialize mints again; mark genuine mints so the service does not
    treat them as FR #3863 reuse.
    """
    text = INSTALL.read_text(encoding="utf-8-sig")
    assert "FR #3900" in text
    assert "prefer prior console.password" in text or "prefer-prior" in text
    assert "console.password-minted" in text or "password-minted" in text
    console = INSTALL_CONSOLE.read_text(encoding="utf-8-sig")
    assert "FR #3900" in console
    assert "migrated console.password" in console or "prefer prior console.password" in console
    assert "password-minted" in console
    assert "minted NickServ GUID" in console
    # Marker Write-Host sits on the mint branch before the keep branch.
    mint_idx = console.index("minted NickServ GUID")
    marker_idx = console.index("password-minted marker")
    keep_idx = console.index("INFO keep $NickServPasswordFile")
    assert mint_idx < marker_idx < keep_idx


def test_fr3900_v1_service_honours_install_mint_marker(tmp_path, monkeypatch):
    """Install-minted GUID must skip SASL (FR #3763), not FR #3863 reuse."""
    guid = "33333333-3333-3333-3333-333333333333"
    (tmp_path / "console.password").write_text(guid + "\n", encoding="utf-8")
    (tmp_path / "console.password-minted").write_text("install\n", encoding="ascii")
    s = make(tmp_path, monkeypatch)
    assert s._nickserv_pw_minted is True
    assert s.nickserv_password == guid
    s.handshake()
    assert not any(l.startswith("AUTHENTICATE") for l in s.sent), s.sent
    assert any("FR #3763" in m and "skip SASL" in m for m in s.logs), s.logs


def test_fr3900_v1_sasl_904_heals_from_airc_install_json_password(tmp_path, monkeypatch):
    """Heal must read PasswordFile from sibling install config\\airc-install.json."""
    wrong = "44444444-4444-4444-4444-444444444444"
    right = "55555555-5555-5555-5555-555555555555"
    home = tmp_path / "home"
    home.mkdir()
    (home / "console.password").write_text(wrong + "\n", encoding="utf-8")
    prior = tmp_path / "prior_admin"
    prior.mkdir()
    (prior / "console.password").write_text(right + "\n", encoding="utf-8")
    cfg = tmp_path / "config"
    cfg.mkdir()
    # Service home is <install>/home; json beside install root.
    install_root = tmp_path
    # Point service home at install_root/home — json at install_root/config.
    import json

    (cfg / "airc-install.json").write_text(
        json.dumps(
            {
                "ConsoleHome": str(prior),
                "PasswordFile": str(prior / "console.password"),
                "MachineId": "walrus",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "empty_profile"))
    Path(os.environ["USERPROFILE"]).mkdir(parents=True)
    s = make(home, monkeypatch)
    assert s.nickserv_password == wrong
    s.on_line(":srv 904 * :SASL authentication failed")
    assert s.nickserv_password == right
    assert (home / "console.password").read_text(encoding="utf-8").strip() == right
    assert any("FR #3900 healed" in m for m in s.logs), s.logs
