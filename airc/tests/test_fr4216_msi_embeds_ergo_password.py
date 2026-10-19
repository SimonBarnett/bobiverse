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


@pytest.mark.skipif(os.name != "nt", reason="Windows only")
def test_fr4216_skipmsi_stage_writes_ergo(tmp_path: Path):
    """-SkipMsi airc stage must produce config\\ergo.password (FAKE_ ok when no secret)."""
    out = tmp_path / "dist"
    out.mkdir()
    ver = "0.0.4216"
    env = os.environ.copy()
    for k in (
        "AIRC_PACK_ERGO_PASSWORD",
        "AGENTIC_IRC_PASSWORD",
        "AIRC_CONSOLE_SERVER_PASSWORD",
    ):
        env.pop(k, None)
    # Empty profile so connect.password is absent; pack embeds FAKE_ under -SkipMsi.
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
    ergo = out / f"airc-{ver}" / "config" / "ergo.password"
    assert ergo.is_file(), list((out / f"airc-{ver}" / "config").iterdir()) if (out / f"airc-{ver}" / "config").is_dir() else list(out.iterdir())
    body = ergo.read_text(encoding="utf-8").strip()
    assert body, "ergo.password must be non-empty"
    assert "embedded config/ergo.password" in out_text or "FR #4216" in out_text
