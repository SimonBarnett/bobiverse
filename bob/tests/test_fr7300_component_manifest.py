"""FR #7300: tray footer + ear source= use component MANIFEST; hotpatch skips root."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import REPO

SCRIPTS = REPO / "bob" / "scripts"
INSTALL = SCRIPTS / "Install-BobTrayHotpatch.ps1"
EAR_SEL = SCRIPTS / "Select-BobEarLaunch.ps1"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
DOCS = REPO / "bob" / "docs" / "bob-tray-dialogs.md"
PS = os.environ.get("BOB_TEST_POWERSHELL") or shutil.which("powershell.exe") or "powershell.exe"

ROOT_FULL = "47465810123456789abcdef0123456789abcde"
TRAY_FULL = "2638ab5e0123456789abcdef0123456789abcdef"
EAR_FULL = "aabbccdd0123456789abcdef0123456789abcdef"


def _mod():
    sys.path.insert(0, str(SCRIPTS))
    import bob_tray_version as m  # noqa: WPS433

    return m


def test_fr7300_footer_prefers_tools_when_root_differs(tmp_path: Path):
    m = _mod()
    (tmp_path / "VERSION").write_text("2.0.0\n", encoding="utf-8")
    (tmp_path / "MANIFEST.json").write_text(
        json.dumps({"source_commit": ROOT_FULL}) + "\n", encoding="utf-8"
    )
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "MANIFEST.json").write_text(
        json.dumps({"source_commit": TRAY_FULL, "product": "bob-tray"}) + "\n",
        encoding="utf-8",
    )
    env = {k: v for k, v in os.environ.items() if k != "BOBIVERSE_BOB_VERSION"}
    assert m.read_deployed_source_sha(tmp_path) == TRAY_FULL[:7]
    label = m.product_version_label(tmp_path, env=env)
    assert TRAY_FULL[:7] in label
    assert ROOT_FULL[:7] not in label
    assert "exe " not in label


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell")
def test_fr7300_hotpatch_leaves_root_manifest_byte_identical(tmp_path: Path):
    root = tmp_path / "bob"
    art = tmp_path / "art"
    for p in (root / "tools", root / "src" / "Public", art / "tools", art / "src" / "Public", art / "assets"):
        p.mkdir(parents=True)
    root_man = {"source_commit": ROOT_FULL, "product": "bob"}
    root_bytes = (json.dumps(root_man) + "\n").encode("utf-8")
    (root / "MANIFEST.json").write_bytes(root_bytes)
    (root / "tools" / "Watch-BobTray.ps1").write_text("# old\n", encoding="utf-8")
    (root / "src" / "Public" / "Get-BobTrayHover.ps1").write_text("# old\n", encoding="utf-8")
    (art / "tools" / "Watch-BobTray.ps1").write_text("# new\n", encoding="utf-8")
    (art / "src" / "Public" / "Get-BobTrayHover.ps1").write_text("# new\n", encoding="utf-8")
    (art / "MANIFEST.json").write_text(
        json.dumps({"source_commit": TRAY_FULL}) + "\n", encoding="utf-8"
    )
    (art / "provenance.txt").write_text(f"source_commit={TRAY_FULL}\n", encoding="utf-8")
    r = subprocess.run(
        [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(INSTALL),
            "-InstallRoot",
            str(root),
            "-ArtifactDir",
            str(art),
            "-BackupDir",
            str(tmp_path / "bak"),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    assert (root / "MANIFEST.json").read_bytes() == root_bytes
    tools_man = json.loads((root / "tools" / "MANIFEST.json").read_text(encoding="utf-8"))
    assert tools_man["source_commit"] == TRAY_FULL


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell")
def test_fr7300_ear_source_prefers_scripts_manifest(tmp_path: Path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "bob-ear.exe").write_bytes(b"MZ")
    (scripts / "MANIFEST.json").write_text(
        json.dumps({"source_commit": EAR_FULL}) + "\n", encoding="utf-8"
    )
    (tmp_path / "MANIFEST.json").write_text(
        json.dumps({"source_commit": ROOT_FULL}) + "\n", encoding="utf-8"
    )
    script = f"""
. '{EAR_SEL}'
$r = Select-BobEarLaunch -ScriptDir '{scripts}' -InstallRoot '{tmp_path}'
Write-Output $r.SourceCommit
"""
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    out = (r.stdout or "").strip().splitlines()[-1].strip()
    assert out == EAR_FULL
    assert ROOT_FULL not in out


def test_fr7300_pins_in_scripts_and_docs():
    inst = INSTALL.read_text(encoding="utf-8")
    assert "FR #7300" in inst
    assert "Never" in inst or "never" in inst
    # must not Copy-Item MANIFEST to Join-Path $root $leaf anymore for write
    assert "Destination (Join-Path $root $leaf)" not in inst.split("FR #7300")[-1].split("Write-Output")[0]
    watch = WATCH.read_text(encoding="utf-8-sig")
    assert "FR #7300" in watch
    docs = DOCS.read_text(encoding="utf-8")
    assert "FR #7300" in docs
    ear = EAR_SEL.read_text(encoding="utf-8")
    assert "FR #7300" in ear
