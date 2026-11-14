"""FR #7394: bob-ear artifact ships Bobiverse-Common.ps1 (dotted by Start-Bob)."""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
from repo_layout import ROOT

EAR_WF = ROOT / ".github" / "workflows" / "build-bob-ear.yml"
INSTALL = ROOT / "bob" / "scripts" / "Install-BobEarExe.ps1"
START = ROOT / "bob" / "scripts" / "Start-Bob.ps1"
COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
EAR_DOCS = ROOT / "bob" / "docs" / "bob-ear.md"
PS = os.environ.get("BOB_TEST_POWERSHELL") or "powershell.exe"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_fr7394_start_bob_dotsources_common():
    t = _text(START)
    assert "Bobiverse-Common.ps1" in t
    assert "Join-Path $scriptDir 'Bobiverse-Common.ps1'" in t or 'Join-Path $scriptDir "Bobiverse-Common.ps1"' in t


def test_fr7394_workflow_packages_common_and_hash():
    text = _text(EAR_WF)
    assert "Bobiverse-Common.ps1" in text
    assert "common/scripts/Bobiverse-Common.ps1" in text.replace("\\", "/") or (
        "common\\scripts\\Bobiverse-Common.ps1" in text
    )
    assert "bobiverse_common_ps1_sha256=" in text
    assert "FR #7394" in text or "7394" in text
    assert "common/scripts/Bobiverse-Common.ps1" in text.replace("\\", "/")


def test_fr7394_install_copies_common():
    t = _text(INSTALL)
    assert "#7394" in t
    assert "Bobiverse-Common.ps1" in t
    assert "bobiverse_common_ps1_sha256" in t


def test_fr7394_docs_mention_common():
    d = _text(EAR_DOCS)
    assert "#7394" in d
    assert "Bobiverse-Common.ps1" in d


def test_fr7394_common_hash_pin():
    h = hashlib.sha256(COMMON.read_bytes()).hexdigest().lower()
    assert len(h) == 64
    assert "Get-FileHash" in _text(EAR_WF)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell install")
def test_fr7394_install_replaces_stale_common(tmp_path: Path):
    art = tmp_path / "bob-ear-artifact"
    art.mkdir()
    payload = b"MZ-fr7394-ear\n"
    exe = art / "bob-ear.exe"
    exe.write_bytes(payload)
    common_src = COMMON.read_bytes()
    (art / "Bobiverse-Common.ps1").write_bytes(common_src)
    (art / "Start-Bob.ps1").write_bytes(START.read_bytes())
    select = ROOT / "bob" / "scripts" / "Select-BobEarLaunch.ps1"
    (art / "Select-BobEarLaunch.ps1").write_bytes(select.read_bytes())
    common_h = hashlib.sha256(common_src).hexdigest().lower()
    exe_h = hashlib.sha256(payload).hexdigest().lower()
    start_h = hashlib.sha256(START.read_bytes()).hexdigest().lower()
    select_h = hashlib.sha256(select.read_bytes()).hexdigest().lower()
    prov = "\n".join(
        [
            "source_commit=abcdef1234567890aaaaaaaaaaaaaaaaaaaaaaaa",
            f"exe_sha256={exe_h}",
            f"start_bob_ps1_sha256={start_h}",
            f"select_bob_ear_launch_ps1_sha256={select_h}",
            f"bobiverse_common_ps1_sha256={common_h}",
            "fr=7394",
        ]
    )
    (art / "provenance.txt").write_text(prov + "\n", encoding="ascii")

    install = tmp_path / "bob"
    scripts = install / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "Bobiverse-Common.ps1").write_text("# OLD Common FR #7394\n", encoding="utf-8")
    (install / "VERSION").write_text("0.9.test\n", encoding="utf-8")

    cmd = (
        f"& '{INSTALL}' -InstallRoot '{install}' -SourceExe '{exe}' "
        f"-ProvenancePath '{art / 'provenance.txt'}' -SkipSmoke; "
        "Write-Output ('CommonHash=' + (Get-FileHash -LiteralPath "
        f"'{scripts / 'Bobiverse-Common.ps1'}' -Algorithm SHA256).Hash.ToLowerInvariant())"
    )
    env = os.environ.copy()
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
    assert f"CommonHash={common_h}" in (r.stdout or "")
    assert (scripts / "Bobiverse-Common.ps1").read_bytes() == common_src
