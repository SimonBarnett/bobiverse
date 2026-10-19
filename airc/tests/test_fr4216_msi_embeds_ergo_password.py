"""FR #4216: airc MSI must embed and install config\\ergo.password.

Joker install partially succeeded without Ergo PASS and could not connect.
Pack-BobiverseRelease airc product always embeds the PASS; Install-Airc fails
closed if the file is still missing after layout; Install-AircConsole seeds
ConsoleHome from the packaged file.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from repo_layout import ROOT

PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
INSTALL = ROOT / "airc" / "scripts" / "Install-Airc.ps1"
CONSOLE = ROOT / "airc" / "scripts" / "Install-AircConsole.ps1"
POST = ROOT / "common" / "docs" / "post-install.md"
OPS = ROOT / "airc" / "docs" / "airc-ops.md"


def test_fr4216_pack_airc_always_embeds():
    t = PACK.read_text(encoding="utf-8-sig")
    assert "FR #4216" in t
    assert "Name -eq 'airc'" in t or '$Name -eq "airc"' in t or "$Name -eq 'airc'" in t
    assert "wantEmbedErgo" in t or "wantEmbed" in t
    assert "AIRC_PACK_ERGO_PASSWORD" in t
    assert "airc pack requires Ergo server PASS" in t
    # bob/jeeves still skip by default (issue #4)
    assert "issue #4" in t
    assert "skipping Ergo PASS embed" in t


def test_fr4216_install_airc_fail_closed_missing_ergo():
    t = INSTALL.read_text(encoding="utf-8-sig")
    assert "FR #4216" in t
    assert "config\\ergo.password missing after MSI layout" in t or "config\\ergo.password missing" in t
    assert "Never invent" in t
    # Must run before Install-AircConsole call path continues with secrets
    assert "AIRC_PACK_ERGO_PASSWORD" in t or "BOB_IRC_PASSWORD" in t


def test_fr4216_install_console_error_cites_embed():
    t = CONSOLE.read_text(encoding="utf-8-sig")
    assert "FR #4216" in t
    assert "embeds" in t.lower() or "embed" in t.lower()
    assert "Never invent" in t


def test_fr4216_docs_state_airc_embeds():
    post = POST.read_text(encoding="utf-8")
    assert "FR #4216" in post
    assert "embed" in post.lower()
    ops = OPS.read_text(encoding="utf-8")
    assert "FR #4216" in ops


def test_fr4477_pack_skipmsi_disables_embed_gate():
    """FR #4477: -SkipMsi test stages must not embed live/placeholder Ergo PASS."""
    t = PACK.read_text(encoding="utf-8-sig")
    assert "FR #4477" in t
    assert re.search(
        r"if\s*\(\s*\$SkipMsi\s*\)\s*\{\s*\$wantEmbedErgo\s*=\s*\$false\s*\}",
        t,
        re.S,
    )
    assert "not embedding config/ergo.password (FR #4477" in t


@pytest.mark.skipif(os.name != "nt", reason="Windows only")
def test_fr4216_skipmsi_stage_does_not_embed_ergo(tmp_path: Path):
    """FR #4477: -SkipMsi airc stage must NOT write config\\ergo.password.

    Real airc MSI packs (no -SkipMsi) still embed under FR #4216; this gate only
    covers disposable test stages so they never copy a live PASS or placeholder.
    """
    out = tmp_path / "dist"
    out.mkdir()
    ver = "0.0.4216"
    env = os.environ.copy()
    for k in (
        "AIRC_PACK_ERGO_PASSWORD",
        "AGENTIC_IRC_PASSWORD",
        "AIRC_CONSOLE_SERVER_PASSWORD",
        "BOB_IRC_PASSWORD",
    ):
        env.pop(k, None)
    fake_home = tmp_path / "home"
    (fake_home / ".grok" / "ergo").mkdir(parents=True)
    env["USERPROFILE"] = str(fake_home)
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(PACK),
        "-Product",
        "airc",
        "-RepoRoot",
        str(ROOT),
        "-OutDir",
        str(out),
        "-Version",
        ver,
        "-SkipMsi",
        "-SkipAircExe",
        "-SkipAircNetworkInstallerExe",
        "-KeepStage",
    ]
    r = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        env=env,
        cwd=str(ROOT),
    )
    out_text = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out_text[-4000:]
    stage = out / f"airc-{ver}"
    assert stage.is_dir(), list(out.iterdir())
    ergo = stage / "config" / "ergo.password"
    assert not ergo.is_file(), "FR #4477: SkipMsi stage must not embed ergo.password"
    assert "FR #4477" in out_text or "not embedding config/ergo.password" in out_text
