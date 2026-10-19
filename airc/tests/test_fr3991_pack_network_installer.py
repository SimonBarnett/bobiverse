"""FR #3991: pack/build wiring for airc-network-installer.exe."""

from __future__ import annotations

from pathlib import Path

from repo_layout import REPO, resolve


def test_build_script_requests_uac_admin():
    text = resolve("airc/scripts/Build-AircNetworkInstaller.ps1").read_text(encoding="utf-8-sig")
    assert "--uac-admin" in text
    assert "airc-network-installer" in text
    assert "airc_network_installer_main.py" in text


def test_pack_stages_network_installer_and_release_asset():
    pack = resolve("common/scripts/Pack-BobiverseRelease.ps1").read_text(encoding="utf-8-sig")
    assert "Build-AircNetworkInstaller.ps1" in pack
    assert "SkipAircNetworkInstallerExe" in pack
    assert "airc-network-installer-$Version.exe" in pack or 'airc-network-installer-$Version.exe' in pack
    assert "airc-network-installer.exe" in pack
    assert "FR #3991" in pack


def test_assert_release_assets_require_network_installer():
    text = resolve("common/scripts/Assert-BobiverseReleaseAssets.ps1").read_text(encoding="utf-8-sig")
    assert "airc-network-installer-" in text
    assert "FR #3991" in text


def test_package_layout_exists():
    root = resolve("airc/scripts/airc_network_installer")
    for name in ("__init__.py", "cli.py", "core.py", "github_msi.py", "install.py", "__main__.py"):
        assert (root / name).is_file(), name
    assert resolve("airc/scripts/airc_network_installer_main.py").is_file()
