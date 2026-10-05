"""FR #2451: release pack FRs that install/smoke on ionos stamp require_machine=ionos."""
from __future__ import annotations

import gitclaim

# Exact #2447-shaped blob (mis-offered to marchhare without needs-ionos).
_FR2447_TITLE = (
    "release: finish bob+airc 0.1.23 MSI pack after Build-BobWatcher "
    "Start-Process redirect fix"
)
_FR2447_BODY = (
    "After #2442 (Build-BobWatcher.ps1 unique stderr redirect), finish packing "
    "bob-watcher and airc 0.1.23 MSIs, Assert-ReleaseAssets, and install+smoke "
    "on ionos if green. jeeves-0.1.23.msi already at C:\\ai\\release-out\\.\n\n"
    "## acceptance\n"
    "1. bob and airc 0.1.23 MSIs built under release-out with VERSION 0.1.23.\n"
    "2. Assert-ReleaseAssets passes for the trio (or document any still-blocked asset).\n"
    "3. If green: install on ionos and smoke /health + tray/crash/maint paths briefly; "
    "note pass/fail in comment.\n"
    "4. No self-MRB.\n"
)


def test_fr2451_issue_2447_blob_pins_ionos():
    assert (
        gitclaim.infer_require_machine(
            title=_FR2447_TITLE,
            body=_FR2447_BODY,
            labels=("feature-request",),
            repo="SimonBarnett/bobiverse",
            ident="#2447",
        )
        == "ionos"
    )


def test_fr2451_body_install_on_ionos_pins():
    assert (
        gitclaim.infer_require_machine(
            title="release: pack bob 0.1.24 MSIs",
            body="acceptance: install on ionos and smoke /health",
            labels=("feature-request",),
        )
        == "ionos"
    )


def test_fr2451_body_install_plus_smoke_on_ionos_pins():
    assert (
        gitclaim.infer_require_machine(
            title="release: finish airc MSI",
            body="Assert-ReleaseAssets, then install+smoke on ionos if green.",
            labels=("feature-request",),
        )
        == "ionos"
    )


def test_fr2451_title_install_on_ionos_pins():
    assert (
        gitclaim.infer_require_machine(
            title="release pack: install on ionos after Assert-ReleaseAssets",
            body="MSIs under release-out",
            labels=("feature-request",),
        )
        == "ionos"
    )


def test_fr2451_release_out_alone_does_not_pin():
    # Building under release-out is fleet-wide; ionos pin needs install/smoke-on-ionos.
    assert (
        gitclaim.infer_require_machine(
            title="release: pack bob MSI to release-out",
            body="Write bob-0.1.23.msi under C:\\ai\\release-out\\ and Assert-ReleaseAssets.",
            labels=("feature-request",),
        )
        == ""
    )


def test_fr2451_bare_ionos_evidence_does_not_repin():
    # FR #1508: body evidence mentioning ionos pins elsewhere must not re-pin.
    assert (
        gitclaim.infer_require_machine(
            title="docs: tip tray SkipTidy",
            body="Related: #2447 was mis-offered; marchhare GIVEUP needs-ionos for ionos install.",
            labels=("feature-request",),
        )
        == ""
    )
