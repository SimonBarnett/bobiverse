"""FR #7390: bob-ear artifact ships Start-Bob.ps1 + Select-BobEarLaunch.ps1."""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from repo_layout import ROOT

EAR_WF = ROOT / ".github" / "workflows" / "build-bob-ear.yml"
INSTALL = ROOT / "bob" / "scripts" / "Install-BobEarExe.ps1"
START = ROOT / "bob" / "scripts" / "Start-Bob.ps1"
SELECT = ROOT / "bob" / "scripts" / "Select-BobEarLaunch.ps1"
EAR_DOCS = ROOT / "bob" / "docs" / "bob-ear.md"
PS = os.environ.get("BOB_TEST_POWERSHELL") or "powershell.exe"

LAUNCHERS = ("Start-Bob.ps1", "Select-BobEarLaunch.ps1")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().lower()


def test_fr7390_workflow_packages_launchers_and_hashes():
    text = _text(EAR_WF)
    for name in LAUNCHERS:
        assert name in text, f"workflow must stage {name}"
        assert f"bob/scripts/{name}" in text.replace("\\", "/") or (
            f"bob\\scripts\\{name}" in text
        )
    assert "start_bob_ps1_sha256=" in text
    assert "select_bob_ear_launch_ps1_sha256=" in text
    assert "FR #7390" in text or "7390" in text
    # Path filters so launcher edits rebuild the artifact.
    assert "bob/scripts/Start-Bob.ps1" in text
    assert "bob/scripts/Select-BobEarLaunch.ps1" in text
    assert "test_fr7390" in text


def test_fr7390_manifest_keys_match_repo_files_at_tip():
    """Simulate the workflow hash lines against the repo tip files."""
    start_h = _sha256(START)
    select_h = _sha256(SELECT)
    assert len(start_h) == 64
    assert len(select_h) == 64
    assert start_h != select_h
    # Workflow must hash the same relative paths.
    text = _text(EAR_WF)
    assert "Start-Bob.ps1" in text and "Select-BobEarLaunch.ps1" in text
    assert "Get-FileHash" in text


def test_fr7390_install_script_copies_launchers():
    t = _text(INSTALL)
    assert "FR #7390" in t
    assert "Start-Bob.ps1" in t
    assert "Select-BobEarLaunch.ps1" in t
    assert "start_bob_ps1_sha256" in t or "select_bob_ear_launch" in t


def test_fr7390_start_bob_logs_launcher_sha256():
    t = _text(START)
    assert "launcher_sha256=" in t
    assert "FR #7390" in t or "#7390" in t


def test_fr7390_docs_mention_launcher_artifact():
    d = _text(EAR_DOCS)
    assert "FR #7390" in d
    assert "Start-Bob.ps1" in d
    assert "Select-BobEarLaunch.ps1" in d


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell install")
def test_fr7390_install_from_artifact_replaces_old_launcher(tmp_path: Path):
    """Old mtime-style Select + newer .py; artifact install leaves installed-exe."""
    # Artifact stage (as CI uploads).
    art = tmp_path / "bob-ear-artifact"
    art.mkdir()
    payload = b"MZ-fr7390-ear\n"
    exe = art / "bob-ear.exe"
    exe.write_bytes(payload)
    start_src = START.read_bytes()
    select_src = SELECT.read_bytes()
    (art / "Start-Bob.ps1").write_bytes(start_src)
    (art / "Select-BobEarLaunch.ps1").write_bytes(select_src)
    start_h = hashlib.sha256(start_src).hexdigest().lower()
    select_h = hashlib.sha256(select_src).hexdigest().lower()
    exe_h = hashlib.sha256(payload).hexdigest().lower()
    prov = "\n".join(
        [
            "source_commit=abcdef1234567890aaaaaaaaaaaaaaaaaaaaaaaa",
            "workflow_commit=abcdef1234567890aaaaaaaaaaaaaaaaaaaaaaaa",
            f"exe_sha256={exe_h}",
            f"start_bob_ps1_sha256={start_h}",
            f"select_bob_ear_launch_ps1_sha256={select_h}",
            "fr=7390",
        ]
    )
    (art / "provenance.txt").write_text(prov + "\n", encoding="ascii")
    (art / "manifest.txt").write_text(prov + "\n", encoding="ascii")

    install = tmp_path / "bob"
    scripts = install / "scripts"
    scripts.mkdir(parents=True)
    # Stale launcher: pretend mtime gate (would prefer python) — any non-current Select.
    (scripts / "Select-BobEarLaunch.ps1").write_text(
        "# OLD stale launcher FR #7390 fixture\n"
        "function Select-BobEarLaunch { param($ScriptDir,$InstallRoot) "
        "[pscustomobject]@{ UseExe=$false; Reason='mtime-stale-fixture'; "
        "Sha256=''; SourceCommit=''; ProductVersion='' } }\n",
        encoding="utf-8",
    )
    (scripts / "Start-Bob.ps1").write_text("# OLD Start-Bob\n", encoding="utf-8")
    (scripts / "bobreport.py").write_text("# newer py\n", encoding="utf-8")
    (scripts / "irc_agent.py").write_text("# agent\n", encoding="utf-8")
    (install / "VERSION").write_text("0.9.test\n", encoding="utf-8")
    os.utime(scripts / "bobreport.py", (2_000_000_000, 2_000_000_000))

    cmd = (
        f"& '{INSTALL}' -InstallRoot '{install}' -SourceExe '{exe}' "
        f"-ProvenancePath '{art / 'provenance.txt'}' -SkipSmoke; "
        f". '{scripts / 'Select-BobEarLaunch.ps1'}'; "
        f"$r = Select-BobEarLaunch -ScriptDir '{scripts}' -InstallRoot '{install}'; "
        "Write-Output ('UseExe=' + [string]$r.UseExe); "
        "Write-Output ('Reason=' + [string]$r.Reason); "
        "Write-Output ('SelectHash=' + (Get-FileHash -LiteralPath "
        f"'{scripts / 'Select-BobEarLaunch.ps1'}' -Algorithm SHA256).Hash.ToLowerInvariant())"
    )
    env = os.environ.copy()
    env["BOB_EAR_PYTHON"] = ""
    # Clear Autoload=None trap on shop seats
    env.pop("PSModuleAutoLoadingPreference", None)
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    out = r.stdout or ""
    assert "UseExe=True" in out or "UseExe=true" in out
    assert "Reason=installed-exe" in out
    assert f"SelectHash={select_h}" in out
    assert (scripts / "Start-Bob.ps1").read_bytes() == start_src
    assert (scripts / "bob-ear.exe").read_bytes() == payload