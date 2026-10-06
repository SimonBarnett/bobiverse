"""Hostile pins for MRB #2950 / FR #2948: MSI ProductVersion wins over stale git VERSION.

Copy-BobiverseVersion must not let InstallRoot\\common\\VERSION clobber the MSI-laid
VERSION when RepoRoot==InstallRoot (msiexec 1603 via Assert-BobiverseInstallVersion).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
INSTALLS = (
    ROOT / "bob" / "scripts" / "Install-Bob.ps1",
    ROOT / "jeeves" / "scripts" / "Install-Jeeves.ps1",
    ROOT / "airc" / "scripts" / "Install-Airc.ps1",
)


def _t(p: Path) -> str:
    assert p.is_file(), p
    text = p.read_text(encoding="utf-8-sig")
    assert text.endswith("\n")
    return text


def test_mrb2950_copy_version_msi_param_before_same_tree_skip():
    text = _t(COMMON)
    fn = text[text.find("function Copy-BobiverseVersion") : text.find("function Get-BobiverseFullPath")]
    assert "FR #2948" in fn
    assert "MsiProductVersion" in fn
    i_msi = fn.find("$want -match")
    if i_msi < 0:
        i_msi = fn.find("MsiProductVersion")
    i_same = fn.find("Test-BobiverseSamePath")
    assert i_msi >= 0
    assert i_same > i_msi
    assert "WriteAllText" in fn or "WriteAllText" in text[text.find("function Copy-BobiverseVersion") :]


def test_mrb2950_installers_forward_msi_product_version():
    for p in INSTALLS:
        t = _t(p)
        assert "-MsiProductVersion $MsiProductVersion" in t, p.name
        assert "Assert-BobiverseInstallVersion" in t, p.name


def test_mrb2950_assert_still_fail_closed_on_mismatch():
    text = _t(COMMON)
    fn = text[text.find("function Assert-BobiverseInstallVersion") :][:1800]
    assert "FR #2564" in fn
    assert "throw" in fn
    assert "expected" in fn.lower()
