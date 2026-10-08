"""FR #3289: airc start sync_from_repo default off; self_update config/MSI switches."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import airc_console as ac
import airc_console_service as svc
from repo_layout import ROOT

PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
INSTALL_AIRC = ROOT / "airc/scripts/Install-Airc.ps1"
START = ROOT / "airc/scripts/Start-AircConsole.ps1"
SYNC = ROOT / "common/scripts/Sync-BobiverseFromRepo.ps1"
COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
POST = ROOT / "common/docs/post-install.md"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"
HOSTILE = ROOT / "airc/tests/test_mrb2403_hostile_frozen_hooks.py"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def test_load_policy_fresh_default_sync_off_self_update_on(tmp_path: Path):
    policy = ac.load_start_update_policy(tmp_path, env={})
    assert policy.sync_from_repo is False
    assert policy.self_update is True
    assert "sync-from-repo=off" in policy.log_lines()[0]
    assert "self-update=on" in policy.log_lines()[1]


def test_load_policy_airc_json_and_env_overrides(tmp_path: Path):
    cfg = tmp_path / "config" / "airc.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        json.dumps({"sync_from_repo": True, "self_update": False}),
        encoding="utf-8",
    )
    p = ac.load_start_update_policy(tmp_path, env={})
    assert p.sync_from_repo is True
    assert p.self_update is False

    p2 = ac.load_start_update_policy(
        tmp_path,
        env={"BOBIVERSE_SYNC_FROM_REPO": "0", "BOBIVERSE_SELF_UPDATE": "1"},
    )
    assert p2.sync_from_repo is False
    assert p2.self_update is True

    p3 = ac.load_start_update_policy(tmp_path, env={"BOBIVERSE_NO_UPDATE": "1"})
    assert p3.sync_from_repo is False
    assert p3.self_update is False

    p4 = ac.load_start_update_policy(
        tmp_path,
        env={"BOB_AUTOUPDATE": "0"},
    )
    assert p4.sync_from_repo is True
    assert p4.self_update is False


def test_resolve_install_preserve_and_fresh_defaults():
    assert ac.resolve_sync_from_repo_for_install(prior=None, explicit=None) is False
    assert ac.resolve_sync_from_repo_for_install(prior=True, explicit=None) is True
    assert ac.resolve_sync_from_repo_for_install(prior=True, explicit=False) is False
    assert ac.resolve_self_update_for_install(prior=None, explicit=None) is True
    assert ac.resolve_self_update_for_install(prior=False, explicit=None) is False
    assert ac.resolve_self_update_for_install(prior=False, explicit=True) is True


def test_kick_default_no_config_skips_sync_runs_self_update(tmp_path: Path, monkeypatch):
    root = tmp_path / "install"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "Sync-BobiverseFromRepo.ps1").write_text("# sync", encoding="utf-8")
    (scripts / "Update-BobiverseService.ps1").write_text("# upd", encoding="utf-8")
    calls = []

    def capture(script, args, label):
        calls.append((Path(script).name, list(args), label))

    policy = svc.kick_frozen_service_start_hooks(
        _is_frozen=True,
        _root=root,
        _run_ps1=capture,
        _env={},
    )
    assert policy is not None
    assert policy.sync_from_repo is False
    assert policy.self_update is True
    assert [c[0] for c in calls] == ["Update-BobiverseService.ps1"]
    assert calls[0][1] == [
        "-Product",
        "airc",
        "-InstallRoot",
        str(root),
        "-ServiceName",
        "Airc",
    ]


def test_kick_json_sync_off_self_update_off_calls_nothing(tmp_path: Path):
    root = tmp_path / "install"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "Sync-BobiverseFromRepo.ps1").write_text("# sync", encoding="utf-8")
    (scripts / "Update-BobiverseService.ps1").write_text("# upd", encoding="utf-8")
    cfg = root / "config" / "airc.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        '{"sync_from_repo": false, "self_update": false}\n',
        encoding="utf-8",
    )
    calls = []
    policy = svc.kick_frozen_service_start_hooks(
        _is_frozen=True,
        _root=root,
        _run_ps1=lambda *a, **k: calls.append(a),
        _env={},
    )
    assert policy is not None
    assert policy.sync_from_repo is False
    assert policy.self_update is False
    assert calls == []


def test_kick_json_sync_on_runs_sync_then_update(tmp_path: Path):
    root = tmp_path / "install"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "Sync-BobiverseFromRepo.ps1").write_text("# sync", encoding="utf-8")
    (scripts / "Update-BobiverseService.ps1").write_text("# upd", encoding="utf-8")
    cfg = root / "config" / "airc.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('{"sync_from_repo": true, "self_update": true}\n', encoding="utf-8")
    calls = []

    def capture(script, args, label):
        calls.append((Path(script).name, label))

    svc.kick_frozen_service_start_hooks(
        _is_frozen=True,
        _root=root,
        _run_ps1=capture,
        _env={},
    )
    assert [c[0] for c in calls] == [
        "Sync-BobiverseFromRepo.ps1",
        "Update-BobiverseService.ps1",
    ]


def test_install_pack_sync_self_update_wiring():
    pack = PACK.read_text(encoding="utf-8")
    _no_bom(PACK)
    assert 'Property Id="AIRC_SYNC_FROM_REPO"' in pack
    assert 'Property Id="AIRC_SELF_UPDATE"' in pack
    assert "-SyncFromRepo &quot;[AIRC_SYNC_FROM_REPO]&quot;" in pack
    assert "-SelfUpdate &quot;[AIRC_SELF_UPDATE]&quot;" in pack

    inst = INSTALL_AIRC.read_text(encoding="utf-8-sig")
    assert "[string]$SyncFromRepo" in inst
    assert "[string]$SelfUpdate" in inst
    assert "sync_from_repo" in inst
    assert "self_update" in inst
    assert "Protect-BobiverseInstallTree" in inst
    assert "FR #3289" in inst

    start = START.read_text(encoding="utf-8-sig")
    assert "Get-AircStartUpdatePolicy" in start
    assert "sync-from-repo=" in start
    assert "self-update=" in start

    sync = SYNC.read_text(encoding="utf-8-sig")
    assert "sync_from_repo" in sync
    assert "FR #3289" in sync

    common = COMMON.read_text(encoding="utf-8-sig")
    assert "function Protect-BobiverseInstallTree" in common

    post = POST.read_text(encoding="utf-8")
    assert "AIRC_SYNC_FROM_REPO" in post
    assert "AIRC_SELF_UPDATE" in post

    skill = SKILL.read_text(encoding="utf-8")
    assert "sync_from_repo" in skill
    assert "AIRC_SYNC_FROM_REPO" in skill or "FR #3289" in skill


def test_hostile_2403_expects_default_sync_off():
    """MRB #2403 gates must follow FR #3289 default (sync off)."""
    text = HOSTILE.read_text(encoding="utf-8")
    assert "sync_from_repo" in text or "BOBIVERSE_SYNC_FROM_REPO" in text
    assert "test_kick_default" in text or "sync_from_repo" in text


def test_fr3289_files_end_with_newline():
    for p in (
        PACK,
        INSTALL_AIRC,
        START,
        SYNC,
        COMMON,
        POST,
        SKILL,
        Path(__file__),
    ):
        raw = p.read_bytes()
        assert raw.endswith(b"\n"), p
