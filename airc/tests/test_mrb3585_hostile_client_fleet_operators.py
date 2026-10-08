"""MRB #3585 hostile pins for FR #3582 client fleet-operators strip."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from repo_layout import ROOT

COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"
POST = ROOT / "common/docs/post-install.md"


def _ps(script: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        cwd=str(ROOT),
    )


def test_mrb3585_source_drops_fleet_operators_after_allowlist():
    t = COMMON.read_text(encoding="utf-8-sig")
    assert "FR #3582" in t
    assert r"config\fleet-operators.txt" in t
    # Contiguous: Add-RemovedPath targets the roster file.
    assert "Add-RemovedPath (Join-Path $root 'config\\fleet-operators.txt')" in t
    skill = SKILL.read_text(encoding="utf-8")
    assert "3582" in skill and "fleet-operators" in skill
    post = POST.read_text(encoding="utf-8")
    assert "3582" in post and "fleet-operators" in post
    assert not SKILL.read_bytes().startswith(b"\xef\xbb\xbf")


@pytest.mark.skipif(os.name != "nt", reason="Windows only")
def test_mrb3585_sibling_config_survives_fleet_operators_strip(tmp_path: Path):
    """Hostile: drop fleet-operators.txt without wiping install-generated config siblings."""
    stage = tmp_path / "client-stage"
    (stage / "config").mkdir(parents=True)
    (stage / "scripts").mkdir()
    (stage / "airc").mkdir()
    (stage / "third_party" / "nssm" / "win64").mkdir(parents=True)
    (stage / "VERSION").write_text("0.0.0\n", encoding="utf-8")
    (stage / "BUILD.json").write_text("{}\n", encoding="utf-8")
    (stage / "config" / "fleet-operators.txt").write_text("bob-leak\n", encoding="utf-8")
    (stage / "config" / "ergo.password").write_text("secret-placeholder\n", encoding="utf-8")
    (stage / "airc" / "airc.exe").write_bytes(b"MZ")
    (stage / "third_party" / "nssm" / "win64" / "nssm.exe").write_bytes(b"MZ")
    (stage / "scripts" / "Install-Airc.ps1").write_text("# stub\n", encoding="utf-8")

    strip = (
        f". '{COMMON}'; "
        f"$null = @(Remove-BobiverseAircClientExtraPayload -InstallRoot '{stage}'); "
        f"$fo = Test-Path -LiteralPath (Join-Path '{stage}' 'config\\fleet-operators.txt'); "
        f"$ep = Test-Path -LiteralPath (Join-Path '{stage}' 'config\\ergo.password'); "
        f"Write-Output ('fleet_ops=' + $(if ($fo) {{'present'}} else {{'gone'}})); "
        f"Write-Output ('ergo_pw=' + $(if ($ep) {{'kept'}} else {{'missing'}}))"
    )
    proc = _ps(strip)
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0, text
    assert "fleet_ops=gone" in text, text
    assert "ergo_pw=kept" in text, text
    assert not (stage / "config" / "fleet-operators.txt").exists()
    assert (stage / "config" / "ergo.password").is_file()
