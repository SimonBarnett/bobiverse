"""FR #6523: isolated_suite_env must not steal pytest tmp_path digest/roster homes."""
from __future__ import annotations

import json
from pathlib import Path

import bobreport
import gh_filer
import registered_machines as rm
from repo_layout import ROOT


def test_fleet_digest_home_keeps_tmp_path_under_build_suite(tmp_path, monkeypatch):
    iso = tmp_path / "iso" / "profile" / ".bobiverse"
    iso.mkdir(parents=True)
    home = tmp_path / "test-home"
    home.mkdir()
    rm.sync_from_chanserv(home, ["#bobiverse", "#marchhare"])
    monkeypatch.setenv("BOBIVERSE_BUILD_SUITE", "1")
    monkeypatch.setenv("BOB_DIGEST_HOME", str(iso))
    assert bobreport.fleet_digest_home(home) == home
    assert bobreport.is_roster_machine(home, "marchhare")


def test_fleet_digest_home_fr69_env_still_wins_when_env_has_roster(tmp_path, monkeypatch):
    chair = tmp_path / ".jeeves"
    digest = tmp_path / "digest"
    chair.mkdir()
    digest.mkdir()
    (chair / "registered-machines.json").write_text(
        json.dumps({"v": 1, "machines": ["win-mpre8vi4u6u"]}), encoding="utf-8"
    )
    rm.sync_from_chanserv(digest, ["#bobiverse", "#marchhare", "#ce-priority-dev1"])
    monkeypatch.setenv("BOBIVERSE_BUILD_SUITE", "1")
    monkeypatch.setenv("BOB_DIGEST_HOME", str(digest))
    monkeypatch.setenv("BOB_HOME", str(chair))
    assert bobreport.fleet_digest_home(chair) == digest
    assert bobreport.is_roster_machine(chair, "marchhare")


def test_gh_token_candidates_install_root_first_when_iso_config_empty(tmp_path, monkeypatch):
    cfg = tmp_path / "iso-config"
    cfg.mkdir()
    monkeypatch.setenv("BOB_CONFIG_DIR", str(cfg))
    monkeypatch.setenv("BOBIVERSE_BUILD_SUITE", "1")
    first = gh_filer._token_candidate_paths()[0]
    # repo_layout ROOT/scripts -> common/scripts; install token is sibling config/
    assert first == (ROOT / "scripts").parent / "config" / "github.token"
