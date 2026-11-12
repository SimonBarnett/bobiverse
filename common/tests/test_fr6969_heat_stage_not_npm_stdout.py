"""FR #6969: airc pack heat must not receive npm-notice stdout as the stage path."""
from __future__ import annotations

from repo_layout import ROOT

PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"


def test_fr6969_npm_ci_stdout_captured_not_leaked():
    p = PACK.read_text(encoding="utf-8")
    assert "FR #6969" in p
    assert "$npmOut = & npm ci --omit=dev --no-fund --no-audit 2>&1" in p
    assert "$npmExit = $LASTEXITCODE" in p
    assert "foreach ($line in @($npmOut))" in p
    bare = "& npm ci --omit=dev --no-fund --no-audit\n"
    assert bare not in p.replace("\r\n", "\n")


def test_fr6969_heat_asserts_stage_is_directory():
    p = PACK.read_text(encoding="utf-8")
    assert "function Assert-BobiverseHeatStagePath" in p
    assert "Assert-BobiverseHeatStagePath -Stage $Stage" in p
    assert p.index("Assert-BobiverseHeatStagePath -Stage $Stage") < p.index("& $heat dir $Stage")
    assert "native command stdout leaked into Stage-Product" in p
    assert "://" in p


def test_fr6969_ps_join_would_make_uri_path():
    """Document why [string]$Stage + npm stdout is HEAT0001."""
    leaked = [
        "npm notice",
        "npm notice Changelog: https://github.com/npm/cli/releases/tag/v12.2.2",
        r"D:\Bobiverse\build-work\x\out\airc-2.0.0",
    ]
    joined = " ".join(leaked)
    assert "://" in joined
    assert "npm notice" in joined
