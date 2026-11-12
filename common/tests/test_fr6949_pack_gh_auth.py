"""FR #6949: step:pack must get GH_TOKEN so FR #6423 can list published releases."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from repo_layout import ROOT

import bobiverse_build as bb

FAKE = "FAKE_GH_TOKEN_FOR_PACK_TESTS"


def _capture():
    seen = []

    def inner(cmd, cwd=None, env=None, timeout=None, *, name="cmd", ref_or_baseline="", log_path=None, **_):
        seen.append((name, dict(env or {})))
        return SimpleNamespace(exit_code=0, timed_out=False, stdout="", name=name)

    return seen, inner


def test_fr6949_pack_is_a_gh_auth_step():
    assert "pack" in bb.GH_AUTH_STEPS
    assert "assert" in bb.GH_AUTH_STEPS
    src = (ROOT / "common" / "scripts" / "bobiverse_build.py").read_text(encoding="utf-8")
    assert "FR #6949" in src
    common = (ROOT / "common" / "scripts" / "Bobiverse-Common.ps1").read_text(encoding="utf-8")
    assert "function Import-BobiverseGhTokenEnv" in common
    assert "Get-BobiverseLatestPublishedVersion" in common
    helper = common[common.index("function Get-BobiverseLatestPublishedVersion") :]
    assert "Import-BobiverseGhTokenEnv" in helper[:1800]


def test_fr6949_pack_step_gets_runner_token(tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", FAKE)
    seen, inner = _capture()
    run = bb.guarded_run_command(tmp_path, [tmp_path / "live"], inner=inner)
    run("x", env={}, name="pack", ref_or_baseline="HEAD")
    env = seen[0][1]
    assert env["GH_TOKEN"] == FAKE and env["GITHUB_TOKEN"] == FAKE


def test_fr6949_suites_still_tokenless(tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", FAKE)
    seen, inner = _capture()
    run = bb.guarded_run_command(tmp_path, [tmp_path / "live"], inner=inner)
    run("x", env={}, name="pytest-common", ref_or_baseline="HEAD")
    assert seen[0][1]["GH_TOKEN"] == "" and seen[0][1]["GITHUB_TOKEN"] == ""
