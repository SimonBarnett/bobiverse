"""MRB #4763 hostile pins for FR #3991 airc-network-installer."""

from __future__ import annotations

import sys
from pathlib import Path

from repo_layout import resolve

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from airc_network_installer.core import msiexec_install_args, AIRC_PROFILE_PROPERTY, SERVICE_NAME
from airc_network_installer.install import install_remote
from airc_network_installer import github_msi


def test_mrb4763_psexec_argv_simons_shape_no_password():
    r = install_remote(
        host="walrus",
        msi_path=Path(r"C:\\Temp\\airc-1.0.2.msi"),
        candidate_version="1.0.2",
        profile="client",
        force=True,
        psexec=r"C:\\Sysinternals\\PsExec.exe",
        username="",
        password="FAKE_secret_must_not_appear",
        log_dir=Path(r"C:\\Temp\\logs"),
        dry_run=True,
    )
    detail = r.detail
    assert "\\walrus" in detail
    assert "-accepteula" in detail
    assert "-h" in detail.split()
    assert "-s" in detail.split()
    assert "msiexec.exe" in detail
    assert "-p" not in detail.split()
    assert "FAKE_secret_must_not_appear" not in detail
    assert f"{AIRC_PROFILE_PROPERTY}=client" in detail


def test_mrb4763_download_latest_uses_releases_latest_api():
    src = resolve("airc/scripts/airc_network_installer/github_msi.py").read_text(encoding="utf-8")
    assert "/releases/latest" in src
    assert "download_latest_airc_msi" in src
    assert "sha256 mismatch" in src


def test_mrb4763_service_and_uac_pins():
    assert SERVICE_NAME == "Airc"
    build = resolve("airc/scripts/Build-AircNetworkInstaller.ps1").read_text(encoding="utf-8-sig")
    assert "--uac-admin" in build
    ops = resolve("airc/docs/airc-ops.md").read_text(encoding="utf-8")
    assert "airc-network-installer" in ops
    assert "AIRC_PROFILE" in ops
