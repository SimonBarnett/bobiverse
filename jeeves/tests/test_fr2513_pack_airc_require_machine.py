"""FR #2513 / #2512: Pack-Airc / airc MSI re-pack cues + hard-pin #2511 -> ionos."""
from __future__ import annotations

import gitclaim

_FR2511_TITLE = (
    "Re-pack airc MSI after Install-AircConsole ASCII/HomePath fix (#2499/#2501)"
)
# Truncated / cue-stripped body (install+smoke phrase missing) — still must pin.
_FR2511_BODY_STALE = (
    "what: PR #2501 fixed Install-AircConsole.ps1 (ASCII punctuation + HomePath) "
    "but did not re-pack airc MSI / Assert-ReleaseAssets.\n"
    "where: airc pack path / release-out; follow-up called out on PR #2501.\n"
    "fix: Pack-Airc (or Pack-BobiverseRelease -Product airc) with fixed script.\n"
)


def test_fr2513_hard_pin_2511_empty_blob():
    assert (
        gitclaim.infer_require_machine(
            title="",
            body="",
            labels=(),
            repo="SimonBarnett/bobiverse",
            ident="#2511",
        )
        == "ionos"
    )


def test_fr2513_pack_airc_body_pins_without_on_ionos():
    assert (
        gitclaim.infer_require_machine(
            title=_FR2511_TITLE,
            body=_FR2511_BODY_STALE,
            labels=("feature-request", "via-intake"),
            repo="SimonBarnett/bobiverse",
            ident="#2511",
        )
        == "ionos"
    )


def test_fr2513_pack_airc_alone_pins():
    assert (
        gitclaim.infer_require_machine(
            title="follow-up: re-pack after script fix",
            body="Run Pack-Airc and drop MSI under release-out.",
            labels=("feature-request",),
        )
        == "ionos"
    )


def test_fr2513_pack_bobiverse_release_product_airc_pins():
    assert (
        gitclaim.infer_require_machine(
            title="release: airc MSI",
            body="Pack-BobiverseRelease -Product airc then Assert-ReleaseAssets.",
            labels=("feature-request",),
        )
        == "ionos"
    )


def test_fr2513_title_repack_airc_msi_pins():
    assert (
        gitclaim.infer_require_machine(
            title="Re-pack airc MSI after Install-AircConsole fix",
            body="Quiet Apply still ships the broken script until a new MSI is built.",
            labels=("feature-request",),
        )
        == "ionos"
    )


def test_fr2513_assert_release_assets_alone_still_unpinned():
    # Keep FR #2451: bare release-out / Assert-ReleaseAssets is not enough.
    assert (
        gitclaim.infer_require_machine(
            title="release: pack bob MSI to release-out",
            body="Write bob-0.1.23.msi under C:\\ai\\release-out\\ and Assert-ReleaseAssets.",
            labels=("feature-request",),
        )
        == ""
    )


def test_fr2513_offer_gap_receipt_pack_airc_cues_does_not_pin():
    # #2512/#2513 mention Pack-Airc as the missing *cue name*, not a pack job.
    assert (
        gitclaim.infer_require_machine(
            title="chair re-offered ionos airc MSI pack #2511 to marchhare-35016",
            body="fix: stamp needs-ionos from Pack-Airc cues; refs #2511 #2512",
            labels=("via-intake",),
            repo="SimonBarnett/bobiverse",
            ident="#2513",
        )
        == ""
    )
