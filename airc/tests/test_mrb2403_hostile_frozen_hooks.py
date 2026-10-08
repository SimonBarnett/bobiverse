"""Hostile MRB #2403: behavioral gates for frozen Sync/Update hooks."""
from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import airc_console_service as svc


def test_resolve_install_root_airc_subdir_layout(tmp_path, monkeypatch):
    """Pack stages airc\\airc.exe under install root (FR #2397 / #2400)."""
    root = tmp_path / 'install'
    exe = root / 'airc' / 'airc.exe'
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b'MZ')
    monkeypatch.setattr(svc, 'is_frozen_airc_exe', lambda: True)
    monkeypatch.setattr(svc.sys, 'executable', str(exe))
    assert svc.resolve_airc_install_root() == root.resolve()


def test_resolve_install_root_flat_exe_parent(tmp_path, monkeypatch):
    root = tmp_path / 'install'
    exe = root / 'airc.exe'
    root.mkdir(parents=True)
    exe.write_bytes(b'MZ')
    monkeypatch.setattr(svc, 'is_frozen_airc_exe', lambda: True)
    monkeypatch.setattr(svc.sys, 'executable', str(exe))
    assert svc.resolve_airc_install_root() == root.resolve()


def test_kick_skips_when_not_frozen(monkeypatch):
    calls = []
    monkeypatch.setattr(svc, 'is_frozen_airc_exe', lambda: False)
    monkeypatch.setattr(svc, '_run_ps1_best_effort', lambda *a, **k: calls.append(a))
    svc.kick_frozen_service_start_hooks()
    assert calls == []


def test_kick_honours_bobiverse_no_update(tmp_path, monkeypatch):
    root = tmp_path / 'install'
    scripts = root / 'scripts'
    scripts.mkdir(parents=True)
    (scripts / 'Sync-BobiverseFromRepo.ps1').write_text('# sync', encoding='utf-8')
    (scripts / 'Update-BobiverseService.ps1').write_text('# upd', encoding='utf-8')
    calls = []
    monkeypatch.setattr(svc, 'is_frozen_airc_exe', lambda: True)
    monkeypatch.setattr(svc, 'resolve_airc_install_root', lambda: root)
    monkeypatch.setattr(svc, '_run_ps1_best_effort', lambda *a, **k: calls.append(a))
    monkeypatch.setenv('BOBIVERSE_NO_UPDATE', '1')
    svc.kick_frozen_service_start_hooks()
    assert calls == []


def test_kick_default_sync_off_self_update_on_when_frozen(tmp_path, monkeypatch):
    """FR #3289: fresh MSI / no airc.json → sync off, self_update on."""
    root = tmp_path / 'install'
    scripts = root / 'scripts'
    scripts.mkdir(parents=True)
    sync = scripts / 'Sync-BobiverseFromRepo.ps1'
    upd = scripts / 'Update-BobiverseService.ps1'
    sync.write_text('# sync', encoding='utf-8')
    upd.write_text('# upd', encoding='utf-8')
    calls = []

    def capture(script, args, label):
        calls.append((Path(script).name, list(args), label))

    monkeypatch.setattr(svc, 'is_frozen_airc_exe', lambda: True)
    monkeypatch.setattr(svc, 'resolve_airc_install_root', lambda: root)
    monkeypatch.setattr(svc, '_run_ps1_best_effort', capture)
    monkeypatch.delenv('BOBIVERSE_NO_UPDATE', raising=False)
    monkeypatch.delenv('BOBIVERSE_SYNC_FROM_REPO', raising=False)
    monkeypatch.delenv('BOBIVERSE_SELF_UPDATE', raising=False)
    svc.kick_frozen_service_start_hooks()
    assert [c[0] for c in calls] == ['Update-BobiverseService.ps1']
    assert calls[0][1] == ['-Product', 'airc', '-InstallRoot', str(root), '-ServiceName', 'Airc']


def test_kick_runs_sync_then_update_when_sync_from_repo_on(tmp_path, monkeypatch):
    """Opt-in fleet: config sync_from_repo=true (or BOBIVERSE_SYNC_FROM_REPO=1)."""
    root = tmp_path / 'install'
    scripts = root / 'scripts'
    scripts.mkdir(parents=True)
    sync = scripts / 'Sync-BobiverseFromRepo.ps1'
    upd = scripts / 'Update-BobiverseService.ps1'
    sync.write_text('# sync', encoding='utf-8')
    upd.write_text('# upd', encoding='utf-8')
    cfg = root / 'config' / 'airc.json'
    cfg.parent.mkdir(parents=True)
    cfg.write_text('{"sync_from_repo": true, "self_update": true}\n', encoding='utf-8')
    calls = []

    def capture(script, args, label):
        calls.append((Path(script).name, list(args), label))

    monkeypatch.setattr(svc, 'is_frozen_airc_exe', lambda: True)
    monkeypatch.setattr(svc, 'resolve_airc_install_root', lambda: root)
    monkeypatch.setattr(svc, '_run_ps1_best_effort', capture)
    monkeypatch.delenv('BOBIVERSE_NO_UPDATE', raising=False)
    svc.kick_frozen_service_start_hooks()
    assert [c[0] for c in calls] == ['Sync-BobiverseFromRepo.ps1', 'Update-BobiverseService.ps1']
    assert calls[0][1] == ['-Product', 'airc', '-InstallRoot', str(root)]
    assert calls[1][1] == ['-Product', 'airc', '-InstallRoot', str(root), '-ServiceName', 'Airc']
