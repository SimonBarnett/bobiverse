"""FR #3393: AIRC_PROFILE=workstation defaults self_update off + locked caps."""
from __future__ import annotations

from pathlib import Path

import airc_console as ac
from repo_layout import ROOT

INSTALL = ROOT / "airc/scripts/Install-Airc.ps1"
POST = ROOT / "common/docs/post-install.md"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def _ascii_only(path: Path) -> None:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    assert all(b < 128 for b in raw), f"non-ASCII in {path}"


def test_resolve_self_update_workstation_defaults_false():
    assert ac.resolve_self_update_for_install(prior=None, explicit=None) is True
    assert (
        ac.resolve_self_update_for_install(
            prior=None, explicit=None, profile="workstation"
        )
        is False
    )
    # Prior true must not keep SYSTEM MSI channel on workstation reinstall.
    assert (
        ac.resolve_self_update_for_install(
            prior=True, explicit=None, profile="workstation"
        )
        is False
    )
    # Explicit MSI/CLI wins over profile.
    assert (
        ac.resolve_self_update_for_install(
            prior=None, explicit=True, profile="workstation"
        )
        is True
    )
    assert (
        ac.resolve_self_update_for_install(
            prior=True, explicit=False, profile="workstation"
        )
        is False
    )


def test_resolve_shell_jobs_update_require_workstation():
    assert (
        ac.resolve_shell_mode_for_install(
            prior_shell="operators",
            explicit=None,
            had_prior_service=True,
            profile="workstation",
        )
        == "off"
    )
    assert (
        ac.resolve_shell_mode_for_install(
            prior_shell=None,
            explicit="operators",
            had_prior_service=False,
            profile="workstation",
        )
        == "operators"
    )
    assert (
        ac.resolve_jobs_for_install(prior="on", explicit=None, profile="workstation")
        == "off"
    )
    assert (
        ac.resolve_jobs_for_install(prior=None, explicit="on", profile="workstation")
        == "on"
    )
    assert ac.resolve_jobs_for_install(prior=None, explicit=None, profile=None) == "on"
    assert (
        ac.resolve_update_cap_for_install(
            prior="on", explicit=None, profile="workstation"
        )
        == "off"
    )
    assert (
        ac.resolve_update_cap_for_install(
            prior=None, explicit="on", profile="workstation"
        )
        == "on"
    )
    assert (
        ac.resolve_update_cap_for_install(prior=None, explicit=None, profile=None)
        == "on"
    )
    assert (
        ac.resolve_require_account_for_install(
            prior=False, explicit=None, profile="workstation"
        )
        is True
    )
    assert (
        ac.resolve_require_account_for_install(
            prior=None, explicit=False, profile="workstation"
        )
        is False
    )
    assert (
        ac.resolve_require_account_for_install(prior=None, explicit=None, profile=None)
        is False
    )


def test_install_airc_wires_workstation_capability_defaults():
    t = INSTALL.read_text(encoding="utf-8")
    _no_bom(INSTALL)
    _ascii_only(INSTALL)
    assert "FR #3393" in t
    assert "$prof -eq 'workstation'" in t
    assert "$resolvedSelf = $false" in t
    assert "$resolvedShell = 'off'" in t
    assert "$resolvedJobs = 'off'" in t
    assert "$resolvedUpdate = 'off'" in t
    assert "$resolvedRequire = $true" in t
    assert "workstation-profile" in t
    assert "enabled = $false" in t
    assert "profile={1}" in t or "profile=" in t


def test_docs_and_skill_document_workstation_self_update_off():
    post = POST.read_text(encoding="utf-8")
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3393" in post
    assert "self_update=false" in post
    assert "AIRC_PROFILE=workstation" in post
    assert "require_account=true" in post
    assert "#3393" in skill
    assert "self_update=false" in skill
    assert "workstation" in skill.lower()
