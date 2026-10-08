"""MRB #3311 hostile pins: sync_from_repo default off; start-update policy (FR #3289)."""
from __future__ import annotations

from pathlib import Path

import airc_console as ac
import airc_console_service as svc

REPO = Path(__file__).resolve().parents[2]
INSTALL = REPO / "airc" / "scripts" / "Install-Airc.ps1"
START = REPO / "airc" / "scripts" / "Start-AircConsole.ps1"
SYNC = REPO / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1"
COMMON = REPO / "common" / "scripts" / "Bobiverse-Common.ps1"
PACK = REPO / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
SKILL = REPO / "airc" / ".grok" / "skills" / "bobiverse-airc" / "SKILL.md"


def test_mrb3311_default_policy_sync_off_self_update_on():
    p = ac.load_start_update_policy(env={})
    assert p.sync_from_repo is False
    assert p.self_update is True
    lines = "\n".join(p.log_lines())
    assert "sync-from-repo=off" in lines
    assert "self-update=on" in lines


def test_mrb3311_kick_frozen_source_gates_on_policy():
    src = Path(svc.__file__).read_text(encoding="utf-8")
    assert "load_start_update_policy" in src
    assert "policy.sync_from_repo" in src
    assert "policy.self_update" in src


def test_mrb3311_install_pack_sync_wiring():
    install = INSTALL.read_text(encoding="utf-8")
    pack = PACK.read_text(encoding="utf-8")
    sync = SYNC.read_text(encoding="utf-8")
    common = COMMON.read_text(encoding="utf-8")
    start = START.read_text(encoding="utf-8")
    assert "Protect-BobiverseInstallTree" in install and "Protect-BobiverseInstallTree" in common
    assert "AIRC_SYNC_FROM_REPO" in pack and "AIRC_SELF_UPDATE" in pack
    assert "sync_from_repo" in install and "Product -eq 'airc'" in sync.replace(" ", "") or (
        "$Product -eq 'airc'" in sync
    )
    assert "sync_from_repo" in start
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3289" in skill and "sync off" in skill.lower()
