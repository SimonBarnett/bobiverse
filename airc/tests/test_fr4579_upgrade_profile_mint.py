"""FR #4579: walrus 1.0.x upgrade - preserve profile, refuse empty-dest mint, PASSWD wording."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

INSTALL = ROOT / "airc" / "scripts" / "Install-Airc.ps1"
SERVICE = ROOT / "airc" / "scripts" / "airc_console_service.py"
OPS = ROOT / "airc" / "docs" / "airc-ops.md"
SKILL = (
    ROOT
    / "airc"
    / ".grok"
    / "skills"
    / "bobiverse-airc-troubleshooting"
    / "SKILL.md"
)


def test_fr4579_preserve_profile_before_fleet_default():
    t = INSTALL.read_text(encoding="utf-8-sig")
    assert "FR #4579" in t
    assert "preserving profile=" in t
    assert "config\\airc.json" in t or r"config\airc.json" in t
    assert "airc-install.json" in t
    i_preserve = t.index("FR #4579 preserving profile=")
    i_default = t.index(
        "if (-not $prof) { $prof = $(if ($wantAgentLayer) { 'fleet' } else { 'workstation' }) }"
    )
    assert i_preserve < i_default


def test_fr4579_refuse_mint_on_upgrade_empty_dest():
    t = INSTALL.read_text(encoding="utf-8-sig")
    assert "upgrade refused to mint a new console.password" in t
    assert "hadPriorInstallForMint" in t
    assert "NickServ PASSWD" in t


def test_fr4579_client_self_update_still_forced_off():
    t = INSTALL.read_text(encoding="utf-8-sig")
    force = "elseif ($prof -in @('workstation', 'client')) { $resolvedSelf = $false }"
    assert force in t


def test_fr4579_logs_and_docs_say_passwd_not_sapasswd():
    svc = SERVICE.read_text(encoding="utf-8")
    assert "manual oper NickServ PASSWD required" in svc
    assert "manual SAPASSWD required" not in svc
    assert "NickServ SAPASSWD" not in svc
    assert "PRIVMSG NickServ :PASSWD" in svc
    ops = OPS.read_text(encoding="utf-8")
    assert "FR #4579" in ops
    assert "NickServ PASSWD" in ops
    # User-facing reclaim path must not teach the non-Ergo SAPASSWD verb.
    assert "oper `NickServ SAPASSWD" not in ops
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #4579" in skill
    assert "PASSWD only, not SAPASSWD" in skill or "not SAPASSWD" in skill
