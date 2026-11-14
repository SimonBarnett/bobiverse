"""FR #6924: tray label = MSI VERSION + deployed provenance short SHA."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import REPO, ROOT

PS = shutil.which("powershell.exe") or shutil.which("powershell") or shutil.which("pwsh")
SCRIPTS = REPO / "bob" / "scripts"
WRITE = SCRIPTS / "Write-BobTrayDeployedIdentity.ps1"
COMMON_CS = REPO / "bob" / "tray" / "dialogs" / "BobDialogsCommon.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
ABOUT = REPO / "bob" / "tray" / "dialogs" / "BobAbout.cs"
STATUS = REPO / "bob" / "tray" / "dialogs" / "BobStatus.cs"
DOCS = REPO / "bob" / "docs" / "bob-tray-dialogs.md"
WF = ROOT / ".github" / "workflows" / "build-bob-tray.yml"
BUILD = SCRIPTS / "Build-BobDialogs.ps1"
SYNC = ROOT / "scripts" / "Sync-BobiverseFromRepo.ps1"
PACK = ROOT / "scripts" / "Pack-BobiverseRelease.ps1"
SHA_FULL = "8622b0399392ec57dba088f6cfe14aa0e8e23b13"
SHA_SHORT = "8622b03"
SHA_HOT = "feedface0123456789abcdef0123456789abcdef"


def _import_mod():
    sys.path.insert(0, str(SCRIPTS))
    import bob_tray_version as m  # noqa: WPS433

    return m


def test_fr6924_version_only_label(tmp_path: Path):
    m = _import_mod()
    (tmp_path / "VERSION").write_text("1.0.3\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "BOBIVERSE_BOB_VERSION"}
    assert m.product_version_label(tmp_path, env=env) == "bob 1.0.3"
    assert m.bob_version_token(tmp_path, env=env) == "1.0.3"
    assert (tmp_path / "VERSION").read_text(encoding="utf-8").startswith("1.0.3")


def test_fr6924_manifest_sha_appended(tmp_path: Path):
    m = _import_mod()
    (tmp_path / "VERSION").write_text("1.0.3\n", encoding="utf-8")
    (tmp_path / "MANIFEST.json").write_text(
        json.dumps({"source_commit": SHA_FULL, "product": "bob"}) + "\n",
        encoding="utf-8",
    )
    env = {k: v for k, v in os.environ.items() if k != "BOBIVERSE_BOB_VERSION"}
    assert m.product_version_label(tmp_path, env=env) == f"bob 1.0.3 ({SHA_SHORT})"
    assert m.bob_version_token(tmp_path, env=env) == f"1.0.3 ({SHA_SHORT})"
    # VERSION / ARP unchanged
    assert (tmp_path / "VERSION").read_text(encoding="utf-8").strip() == "1.0.3"


def test_fr6924_provenance_fallback_and_msi_2_0_0(tmp_path: Path):
    m = _import_mod()
    (tmp_path / "VERSION").write_text("2.0.0\n", encoding="utf-8")
    (tmp_path / "provenance.txt").write_text(
        f"workflow_commit={SHA_FULL}\nbuilder=Build-BobDialogs.ps1\n",
        encoding="utf-8",
    )
    env = {k: v for k, v in os.environ.items() if k != "BOBIVERSE_BOB_VERSION"}
    assert m.product_version_label(tmp_path, env=env).startswith("bob 2.0.0")
    assert m.product_version_label(tmp_path, env=env) == f"bob 2.0.0 ({SHA_SHORT})"


def test_fr6924_hotpatch_updates_sha_keeps_version(tmp_path: Path):
    m = _import_mod()
    (tmp_path / "VERSION").write_text("2.0.0\n", encoding="utf-8")
    (tmp_path / "MANIFEST.json").write_text(
        json.dumps({"source_commit": SHA_FULL}) + "\n", encoding="utf-8"
    )
    env = {k: v for k, v in os.environ.items() if k != "BOBIVERSE_BOB_VERSION"}
    assert m.product_version_label(tmp_path, env=env) == f"bob 2.0.0 ({SHA_SHORT})"
    (tmp_path / "HOTPATCH.json").write_text(
        json.dumps({"commit": SHA_HOT, "hotpatched_utc": "2026-11-12T00:00:00Z"}) + "\n",
        encoding="utf-8",
    )
    # MANIFEST still wins over HOTPATCH
    assert m.product_version_label(tmp_path, env=env) == f"bob 2.0.0 ({SHA_SHORT})"
    # Simulated hotpatch that rewrites identity only
    (tmp_path / "MANIFEST.json").write_text(
        json.dumps({"source_commit": SHA_HOT}) + "\n", encoding="utf-8"
    )
    assert m.product_version_label(tmp_path, env=env) == "bob 2.0.0 (feedfac)"
    assert (tmp_path / "VERSION").read_text(encoding="utf-8").strip() == "2.0.0"


def test_fr6924_hotpatch_json_when_no_manifest(tmp_path: Path):
    m = _import_mod()
    (tmp_path / "VERSION").write_text("2.0.0\n", encoding="utf-8")
    (tmp_path / "HOTPATCH.json").write_text(
        json.dumps({"hotpatch_commit": SHA_HOT}) + "\n", encoding="utf-8"
    )
    env = {k: v for k, v in os.environ.items() if k != "BOBIVERSE_BOB_VERSION"}
    assert m.product_version_label(tmp_path, env=env) == "bob 2.0.0 (feedfac)"


@pytest.mark.skipif(not PS, reason="needs powershell")
def test_fr6924_writer_pins_manifest_and_provenance(tmp_path: Path):
    m = _import_mod()
    (tmp_path / "VERSION").write_text("2.0.0\n", encoding="utf-8")
    (tmp_path / "tools").mkdir()
    r = subprocess.run(
        [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(WRITE),
            "-InstallRoot",
            str(tmp_path),
            "-Commit",
            SHA_FULL,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    man = json.loads((tmp_path / "MANIFEST.json").read_text(encoding="utf-8"))
    assert man["source_commit"] == SHA_FULL
    assert man["short_sha"] == SHA_SHORT
    prov = (tmp_path / "provenance.txt").read_text(encoding="utf-8")
    assert f"workflow_commit={SHA_FULL}" in prov or f"source_commit={SHA_FULL}" in prov
    assert (tmp_path / "tools" / "provenance.txt").is_file()
    tools_man = json.loads((tmp_path / "tools" / "MANIFEST.json").read_text(encoding="utf-8"))
    assert tools_man["source_commit"] == SHA_FULL
    env = {k: v for k, v in os.environ.items() if k != "BOBIVERSE_BOB_VERSION"}
    assert m.product_version_label(tmp_path, env=env) == f"bob 2.0.0 ({SHA_SHORT})"
    assert (tmp_path / "VERSION").read_text(encoding="utf-8").strip() == "2.0.0"


def test_fr6924_csharp_and_ps_readers_agree_on_sources():
    cs = COMMON_CS.read_text(encoding="utf-8-sig")
    assert "MANIFEST.json" in cs
    assert "provenance.txt" in cs
    assert "HOTPATCH.json" in cs
    assert "BUILD.json" in cs
    assert "source_commit" in cs
    assert "workflow_commit" in cs
    assert "BobVersion" in cs
    # Must re-read identity when UI is shown (not cache-only at process start).
    about = ABOUT.read_text(encoding="utf-8-sig")
    status = STATUS.read_text(encoding="utf-8-sig")
    assert "BobVersion" in about and "BobVersion" in status
    assert "Shown" in about or "BobVersion(root)" in about
    assert "BobVersion(root)" in status

    watch = WATCH.read_text(encoding="utf-8-sig")
    assert "function Get-BobTrayProductVersionLabel" in watch
    assert "MANIFEST.json" in watch
    assert "provenance.txt" in watch
    assert "HOTPATCH.json" in watch
    fn = watch[watch.index("function Get-BobTrayProductVersionLabel") :]
    fn = fn[: fn.index("\nfunction ")]
    assert "bob {" in fn or "bob {0}" in fn
    assert "short" in fn.lower() or "Substring(0, 7)" in fn or ".Substring(0,7)" in fn.replace(" ", "")


def test_fr6924_writers_and_ci_pins():
    assert WRITE.is_file()
    build = BUILD.read_text(encoding="utf-8")
    assert "Write-BobTrayDeployedIdentity" in build
    sync = SYNC.read_text(encoding="utf-8-sig")
    assert "Write-BobTrayDeployedIdentity" in sync
    pack = PACK.read_text(encoding="utf-8-sig")
    assert "Write-BobTrayDeployedIdentity" in pack or "MANIFEST.json" in pack
    wf = WF.read_text(encoding="utf-8")
    assert "provenance.txt" in wf
    assert "MANIFEST.json" in wf
    assert "source_commit" in wf or "Write-BobTrayDeployedIdentity" in wf
    docs = DOCS.read_text(encoding="utf-8-sig")
    assert "FR #6924" in docs
    assert "MANIFEST.json" in docs
    assert "provenance" in docs.lower()
    assert "hotpatch" in docs.lower()
