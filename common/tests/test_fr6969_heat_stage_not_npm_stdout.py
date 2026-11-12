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


def test_fr6975_skipmsi_skips_npm_ci():
    """FR #6975: stage-only airc pack must not require npm (agent-layer BUILD)."""
    p = PACK.read_text(encoding="utf-8")
    assert "FR #6975" in p
    assert "-SkipMsi skip npm ci" in p
    npm_ci_at = p.index("$npmOut = & npm ci --omit=dev")
    skip_at = p.index("-SkipMsi skip npm ci")
    pw = p.index("# FR #5283 / #5905")
    assert pw < skip_at < npm_ci_at


def test_fr6978_skipmsi_seeds_stub_priority_web_sdk():
    """FR #6978: SkipMsi still stages node_modules/priority-web-sdk for client allowlist."""
    p = PACK.read_text(encoding="utf-8")
    assert "FR #6978" in p
    assert "seeded stub node_modules/priority-web-sdk" in p
    assert '0.0.0-skipmsi' in p
    # Stub is stage-only under $pwDest, after the copy loop, never under repo $pwSrc.
    seed_at = p.index("seeded stub node_modules/priority-web-sdk")
    dest_at = p.index("$nmDest = Join-Path $pwDest")
    copy_end = p.index("INFO airc staged airc\\priority-worker (FR #5283/#5905)")
    assert dest_at < seed_at < copy_end
    assert "Set-Content -LiteralPath $stubPkg" in p
    assert "never mutate the repo tree" in p or "stage-only stub" in p


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
