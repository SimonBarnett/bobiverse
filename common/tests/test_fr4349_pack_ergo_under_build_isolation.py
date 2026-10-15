"""FR #4349: airc pack under !build isolation must still find Ergo PASS.

Release BUILD runs pack via guarded_run_command, which sets a fake USERPROFILE
and blanks AGENTIC_IRC_PASSWORD / BOB_IRC_PASSWORD (#4183). FR #4216 requires
airc MSI to embed config\\ergo.password; without fleet-path / pack-secret
injection, step:pack fails closed (release-blocker #4349).
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bobiverse_build as bb  # noqa: E402

from repo_layout import ROOT

PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"

FAKE_PASS = "FAKE_ERGO_PASS_FOR_FR4349_TESTS"


def test_fr4349_pack_searches_fleet_install_paths():
    t = PACK.read_text(encoding="utf-8-sig")
    assert "FR #4349" in t
    assert "Get-BobiverseAiRoot" in t
    assert "@('bob', 'airc', 'jeeves')" in t or '@("bob", "airc", "jeeves")' in t
    assert r"$prod\config\ergo.password" in t or "$prod\\config\\ergo.password" in t
    assert "BOB_IRC_PASSWORD" in t
    # Isolation-safe: profile connect.password alone is not enough for !build pack
    assert ".grok" in t and "connect.password" in t


def test_fr4349_pack_secret_steps_named():
    assert "pack" in bb.PACK_SECRET_STEPS


def test_fr4349_pack_ergo_env_from_env(monkeypatch):
    monkeypatch.delenv("AIRC_PACK_ERGO_PASSWORD", raising=False)
    monkeypatch.delenv("AGENTIC_IRC_PASSWORD", raising=False)
    monkeypatch.delenv("AIRC_CONSOLE_SERVER_PASSWORD", raising=False)
    monkeypatch.delenv("BOB_IRC_PASSWORD", raising=False)
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", FAKE_PASS)
    got = bb.pack_ergo_env()
    assert got == {"AIRC_PACK_ERGO_PASSWORD": FAKE_PASS}


def test_fr4349_pack_ergo_env_from_fleet_file(tmp_path, monkeypatch):
    monkeypatch.delenv("AIRC_PACK_ERGO_PASSWORD", raising=False)
    monkeypatch.delenv("AGENTIC_IRC_PASSWORD", raising=False)
    monkeypatch.delenv("AIRC_CONSOLE_SERVER_PASSWORD", raising=False)
    monkeypatch.delenv("BOB_IRC_PASSWORD", raising=False)
    fake_home = tmp_path / "nouser"
    fake_home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    ai = tmp_path / "ai"
    cfg = ai / "bob" / "config"
    cfg.mkdir(parents=True)
    (cfg / "ergo.password").write_text(FAKE_PASS + "\n", encoding="utf-8")
    monkeypatch.setenv("BOB_AI_ROOT", str(ai))
    got = bb.pack_ergo_env()
    assert got.get("AIRC_PACK_ERGO_PASSWORD") == FAKE_PASS


def test_fr4349_pack_step_gets_secret_after_isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRC_PACK_ERGO_PASSWORD", FAKE_PASS)
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "FAKE_SHOULD_STAY_BLANK_IN_SUITE")
    monkeypatch.setenv("BOB_IRC_PASSWORD", "FAKE_SHOULD_STAY_BLANK_IN_SUITE")
    seen = []

    def inner(cmd, cwd=None, env=None, timeout=None, *, name="cmd", ref_or_baseline=""):
        seen.append((name, dict(env or {})))
        return SimpleNamespace(exit_code=0, timed_out=False, stdout="", name=name)

    run = bb.guarded_run_command(tmp_path, [tmp_path / "live"], inner=inner)
    run("pack-cmd", env={}, name="pack", ref_or_baseline="HEAD")
    env = seen[0][1]
    assert env.get("AIRC_PACK_ERGO_PASSWORD") == FAKE_PASS
    # Suites isolation still blanks these; pack uses AIRC_PACK only
    assert env.get("AGENTIC_IRC_PASSWORD") == ""
    assert env.get("BOB_IRC_PASSWORD") == ""


def test_fr4349_suite_steps_do_not_get_pack_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRC_PACK_ERGO_PASSWORD", FAKE_PASS)
    seen = []

    def inner(cmd, cwd=None, env=None, timeout=None, *, name="cmd", ref_or_baseline=""):
        seen.append((name, dict(env or {})))
        return SimpleNamespace(exit_code=0, timed_out=False, stdout="", name=name)

    run = bb.guarded_run_command(tmp_path, [tmp_path / "live"], inner=inner)
    run("pytest", env={}, name="airc", ref_or_baseline="HEAD")
    assert "AIRC_PACK_ERGO_PASSWORD" not in seen[0][1]
