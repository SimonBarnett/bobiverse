"""FR #3991: airc-network-installer helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from airc_network_installer.core import (  # noqa: E402
    AIRC_PROFILE_PROPERTY,
    DEFAULT_PROFILE,
    SERVICE_NAME,
    assert_password_not_in_argv,
    classify_msiexec_exit,
    compare_versions,
    dedupe_hosts,
    msiexec_install_args,
    parse_hosts_csv,
    parse_version,
    planned_action,
)
from airc_network_installer.github_msi import parse_sha256_sidecar  # noqa: E402
from airc_network_installer.cli import build_parser, main  # noqa: E402


def test_service_and_profile_constants():
    assert SERVICE_NAME == "Airc"
    assert AIRC_PROFILE_PROPERTY == "AIRC_PROFILE"
    assert DEFAULT_PROFILE == "client"


def test_parse_and_compare_versions():
    assert parse_version("1.0.2") == (1, 0, 2)
    assert compare_versions("1.0.1", "1.0.2") < 0
    assert compare_versions("1.0.2", "1.0.2") == 0
    assert compare_versions("1.0.3", "1.0.2") > 0


def test_planned_action_skip_upgrade_install():
    assert planned_action(installed="1.0.2", candidate="1.0.2", present=True) == "skip"
    assert planned_action(installed="1.0.1", candidate="1.0.2", present=True) == "upgrade"
    assert planned_action(installed=None, candidate="1.0.2", present=False) == "install"
    assert planned_action(installed="1.0.2", candidate="1.0.2", present=True, force=True) == "upgrade"


def test_classify_msiexec_exit():
    assert classify_msiexec_exit(0) == "success"
    assert classify_msiexec_exit(3010) == "reboot_required"
    assert classify_msiexec_exit(1603) == "failed"


def test_msiexec_args_include_profile_property():
    args = msiexec_install_args(
        msi_local_path=r"C:\Temp\airc-1.0.2.msi",
        log_local_path=r"C:\Temp\airc-1.0.2-install.log",
        profile="client",
    )
    assert args[0] == "msiexec.exe"
    assert "/qn" in args
    assert "/norestart" in args
    assert f"{AIRC_PROFILE_PROPERTY}=client" in args
    assert args[args.index("/i") + 1] == r"C:\Temp\airc-1.0.2.msi"


def test_parse_hosts_and_dedupe_local():
    assert parse_hosts_csv("a, b;c") == ["a", "b", "c"]
    hosts = dedupe_hosts(
        ["BOX", "other", "box.domain", "BOX"],
        local_names=["BOX", "box.domain"],
    )
    assert hosts[0].lower().startswith("box")
    assert hosts.count("other") == 1
    assert len([h for h in hosts if h.lower().startswith("box")]) == 1


def test_password_never_in_argv_helper():
    assert_password_not_in_argv(["psexec", r"\\h", "-accepteula", "-h", "-s"], "s3cret")
    with pytest.raises(AssertionError):
        assert_password_not_in_argv(["psexec", "-p", "s3cret"], "s3cret")


def test_cli_refuses_password_flag():
    assert main(["-p", "nope"]) == 2
    assert main(["--password", "nope"]) == 2


def test_cli_selftest():
    assert main(["--selftest"]) == 0


def test_parser_defaults_profile_client():
    ns = build_parser().parse_args([])
    assert ns.profile == "client"


def test_parse_sha256_sidecar():
    text = "abc123def456  airc-1.0.2.msi\n"
    # need 64 hex - pad
    h = "a" * 64
    text = f"{h}  airc-1.0.2.msi\n"
    assert parse_sha256_sidecar(text, "airc-1.0.2.msi") == h
