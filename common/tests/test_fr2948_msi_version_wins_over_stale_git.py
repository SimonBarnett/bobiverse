"""FR #2948: MSI ProductVersion must win over stale InstallRoot\\common\\VERSION.

Copy-BobiverseVersion used Get-BobiverseRepoPath → common\\VERSION when the install
dir is a split work tree (RepoRoot == InstallRoot). That overwrote the MSI-laid
VERSION and Assert-BobiverseInstallVersion threw → msiexec 1603.
"""
from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_copy_bobiverse_version_accepts_msi_product_version_param():
    t = _read(COMMON)
    fn = t[t.index("function Copy-BobiverseVersion") : t.index("function Get-BobiverseFullPath")]
    assert "MsiProductVersion" in fn
    assert "FR #2948" in fn
    assert "RepoRoot==InstallRoot" in fn or "same path" in fn.lower() or "Test-BobiverseSamePath" in fn


def test_install_scripts_forward_msi_product_version_to_copy():
    for rel in (
        "bob/scripts/Install-Bob.ps1",
        "jeeves/scripts/Install-Jeeves.ps1",
        "airc/scripts/Install-Airc.ps1",
    ):
        t = _read(ROOT / rel)
        assert "Copy-BobiverseVersion" in t
        assert "-MsiProductVersion $MsiProductVersion" in t, rel


def test_pin_stale_common_version_msi_product_version_wins(tmp_path: Path):
    """Acceptance: stale common\\VERSION + -MsiProductVersion → VERSION + Assert OK."""
    install = tmp_path / "airc"
    (install / "common").mkdir(parents=True)
    (install / "common" / "VERSION").write_text("0.1.22\n", encoding="utf-8")
    # MSI heat already laid the new VERSION before RunInstall (then Copy used to clobber it).
    (install / "VERSION").write_text("0.1.25\n", encoding="utf-8")
    common_ps1 = COMMON.resolve()
    ps = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{common_ps1}'
        $root = '{install}'
        Copy-BobiverseVersion -InstallRoot $root -RepoRoot $root -MsiProductVersion '0.1.25'
        $got = (Get-Content -LiteralPath (Join-Path $root 'VERSION') -Raw).Trim()
        if ($got -ne '0.1.25') {{ throw "VERSION=$got expected 0.1.25" }}
        Assert-BobiverseInstallVersion -InstallRoot $root -ExpectedVersion '0.1.25' -Product airc
        Write-Output "OK $got"
        """
    ).strip()
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "OK 0.1.25" in (r.stdout or "")
    assert (install / "VERSION").read_text(encoding="utf-8").strip() == "0.1.25"


def test_pin_same_tree_keeps_laid_version_without_msi_param(tmp_path: Path):
    """When MSI param empty but VERSION already laid and common lags, keep laid."""
    install = tmp_path / "jeeves"
    (install / "common").mkdir(parents=True)
    (install / "common" / "VERSION").write_text("0.1.22\n", encoding="utf-8")
    (install / "VERSION").write_text("0.1.25\n", encoding="utf-8")
    common_ps1 = COMMON.resolve()
    ps = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{common_ps1}'
        $root = '{install}'
        Copy-BobiverseVersion -InstallRoot $root -RepoRoot $root
        $got = (Get-Content -LiteralPath (Join-Path $root 'VERSION') -Raw).Trim()
        if ($got -ne '0.1.25') {{ throw "VERSION=$got expected 0.1.25 (keep laid)" }}
        Write-Output "OK $got"
        """
    ).strip()
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert (install / "VERSION").read_text(encoding="utf-8").strip() == "0.1.25"
