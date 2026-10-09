"""FR #3716: already-locked -Recurse without -Force skips the per-item ACL walk."""
from __future__ import annotations

import re

from repo_layout import ROOT

COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
INSTALL = ROOT / "airc/scripts/Install-Airc.ps1"


def test_fr3716_common_skip_acl_walk_unless_force():
    t = COMMON.read_text(encoding="utf-8-sig")
    assert "FR #3716" in t
    assert "skip ACL walk" in t
    assert "[switch]$Force" in t
    assert "-not $Force" in t
    # Fast path still logs the FR #3678 takeown skip line.
    assert "FR #3678 skip takeown" in t


def test_fr3716_install_airc_full_recurse_passes_force():
    t = INSTALL.read_text(encoding="utf-8-sig")
    assert "FR #3716" in t
    hits = list(
        re.finditer(
            r"Protect-BobiverseInstallTree -Path \$InstallRoot -Recurse -Force -FailClosed",
            t,
        )
    )
    assert len(hits) == 1
    early = t.find("Protect-BobiverseInstallTree -Path $InstallRoot -FailClosed")
    assert early > 0
    assert "-Recurse" not in t[early : early + 80]
