"""FR #6423: tip common/VERSION on 1.0.x; pack refuses ProductVersion downgrade."""
from __future__ import annotations

import subprocess
from pathlib import Path

from repo_layout import ROOT

COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
VERSION = ROOT / "common" / "VERSION"
VISION = ROOT / "common" / "docs" / "vision.md"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr6423_tip_version_on_1_0_line_at_or_above_1_0_8():
    raw = VERSION.read_text(encoding="utf-8").strip()
    parts = [int(x) for x in raw.split(".")]
    assert len(parts) >= 3, raw
    assert (parts[0], parts[1], parts[2]) >= (1, 0, 8), raw


def test_fr6423_common_helpers_and_pack_gate_present():
    c = _read(COMMON)
    assert "function Compare-BobiverseVersion" in c
    assert "function Get-BobiverseLatestPublishedVersion" in c
    assert "function Assert-BobiversePackVersionNotDowngrade" in c
    assert "FR #6423" in c
    # WinPS 5.1 JSON-array parse (space-joined .tagName trap).
    assert "Out-String" in c[c.index("Get-BobiverseLatestPublishedVersion") :]
    assert "ConvertFrom-Json -InputObject" in c[c.index("Get-BobiverseLatestPublishedVersion") :]

    p = _read(PACK)
    assert "Assert-BobiversePackVersionNotDowngrade" in p
    assert "SkipPublishedVersionCheck" in p
    assert "LatestPublishedVersion" in p
    assert "-not $SkipMsi" in p
    v = _read(VISION)
    assert "FR #6423" in v
    assert "common/VERSION" in v


def test_fr6423_compare_and_assert_refuse_downgrade(tmp_path: Path):
    ps1 = tmp_path / "fr6423.ps1"
    common_path = str(COMMON).replace("'", "''")
    ps1.write_text(
        "\n".join(
            [
                "$ErrorActionPreference = 'Stop'",
                f". '{common_path}'",
                "if ((Compare-BobiverseVersion -Left '0.1.25' -Right '1.0.7') -ge 0) { throw '0.1.25 must be < 1.0.7' }",
                "if ((Compare-BobiverseVersion -Left '1.0.8' -Right '1.0.7') -le 0) { throw '1.0.8 must be > 1.0.7' }",
                "if ((Compare-BobiverseVersion -Left '1.0.7' -Right 'v1.0.7') -ne 0) { throw '1.0.7 must equal v1.0.7' }",
                "Assert-BobiversePackVersionNotDowngrade -Version '1.0.8' -LatestPublishedVersion '1.0.7'",
                "$failed = $false",
                "try {",
                "  Assert-BobiversePackVersionNotDowngrade -Version '0.1.25' -LatestPublishedVersion '1.0.7'",
                "} catch {",
                "  $failed = $true",
                "  if ($_.Exception.Message -notmatch 'FR #6423') { throw }",
                "}",
                "if (-not $failed) { throw 'expected downgrade throw' }",
                "Write-Output 'OK fr6423'",
                "",
            ]
        ),
        encoding="utf-8",
    )
    r = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ps1),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(ROOT),
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "OK fr6423" in (r.stdout or "")
