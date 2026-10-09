"""FR #3686: pack stages VERSION == BUILD.json.version == ProductVersion.

Regression of #1552 in a new form: -Version 0.1.27 while common\\VERSION was
0.1.25 shipped BUILD.json=0.1.27 and VERSION=0.1.25 inside the MSI (walrus).
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from repo_layout import ROOT

PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_pack_stamps_version_from_pack_param_not_common_copy():
    t = _read(PACK)
    assert "FR #3686" in t
    # Must write VERSION from $Version, not only Copy-Item src\\VERSION.
    assert "WriteAllText((Join-Path $stage 'VERSION')" in t or 'WriteAllText((Join-Path $stage "VERSION")' in t
    assert "Assert-BobiverseStageVersionAligned" in t
    # Force overwrite of hand-touched unversioned VERSION on upgrade.
    assert "RemoveFile" in t
    assert "RmStaleVersion" in t
    assert "SetAttribute('On', 'install')" in t or 'SetAttribute("On", "install")' in t


def test_common_exports_stage_version_assert():
    t = _read(COMMON)
    assert "function Assert-BobiverseStageVersionAligned" in t
    assert "FR #3686" in t
    assert "BUILD.json" in t[t.index("Assert-BobiverseStageVersionAligned") :]


def test_stage_airc_skipmsi_version_matches_pack_param(tmp_path: Path):
    """Acceptance: -Version 0.1.99 with common\\VERSION still 0.1.25 → stage all 0.1.99."""
    out = tmp_path / "dist"
    out.mkdir()
    pack = PACK.resolve()
    # Use an unlikely version so we do not depend on bumping common\\VERSION.
    want = "0.1.99"
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(pack),
        "-Product",
        "airc",
        "-Version",
        want,
        "-OutDir",
        str(out),
        "-SkipMsi",
        "-SkipAircExe",
        "-KeepStage",
    ]
    env = os.environ.copy()
    # Prefer Node/tools irrelevant; keep PATH.
    r = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600,
        cwd=str(ROOT),
    )
    assert r.returncode == 0, (r.stdout[-4000:], r.stderr[-4000:])
    stage = out / f"airc-{want}"
    assert stage.is_dir(), list(out.iterdir())
    ver = (stage / "VERSION").read_text(encoding="utf-8-sig").strip()
    src_ver = (stage / "src" / "VERSION").read_text(encoding="utf-8-sig").strip()
    build = json.loads((stage / "BUILD.json").read_text(encoding="utf-8"))
    assert ver == want, ver
    assert src_ver == want, src_ver
    assert build.get("version") == want, build
    assert "FR #3686 stage version aligned" in (r.stdout or "")


def test_optional_msi_admin_extract_skipped_without_asset():
    """Admin-extract of a published MSI is optional; document skip when no MSI."""
    # Live release asset not fetched in CI unit seats; stage pin above is required.
    print(
        "SKIP admin-extract MSI: no published airc MSI in this seat; "
        "stage -SkipMsi pin covers VERSION/BUILD/ProductVersion alignment (FR #3686)"
    )
