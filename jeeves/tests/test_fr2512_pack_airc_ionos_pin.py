"""FR #2512: Pack-Airc + install/smoke on ionos must stamp require_machine=ionos (#2511 class)."""
from __future__ import annotations

import gitclaim

_FR2511_TITLE = (
    "Re-pack airc MSI after Install-AircConsole ASCII/HomePath fix (#2499/#2501)"
)
_FR2511_BODY = (
    "what: PR #2501 fixed Install-AircConsole.ps1 (ASCII punctuation + $HomePath) "
    "but did not re-pack airc MSI / Assert-ReleaseAssets. Quiet Apply of airc-0.1.23.msi "
    "still ships the broken script until a new MSI is built.\n"
    "where: airc pack path / release-out; follow-up called out on PR #2501.\n"
    "evidence: MRB #2501 PASS; issue #2499 closed; ionos Apply still needs new MSI "
    "for CA to succeed from package.\n"
    "fix: Pack-Airc (or Pack-BobiverseRelease -Product airc) with fixed script, "
    "Assert-ReleaseAssets, install+smoke on ionos (require_machine=ionos).\n"
)


def test_fr2512_issue_2511_blob_pins_ionos():
    assert (
        gitclaim.infer_require_machine(
            title=_FR2511_TITLE,
            body=_FR2511_BODY,
            labels=("feature-request", "via-intake"),
            repo="SimonBarnett/bobiverse",
            ident="#2511",
        )
        == "ionos"
    )


def test_fr2512_hard_pin_2511():
    assert (
        gitclaim._REQUIRE_MACHINE_ISSUE_PINS.get(
            ("simonbarnett/bobiverse", "#2511")
        )
        == "ionos"
    )


def test_fr2512_pack_airc_assert_install_combo_pins():
    assert (
        gitclaim.infer_require_machine(
            title="Re-pack airc MSI",
            body="Pack-Airc then Assert-ReleaseAssets and install+smoke on ionos.",
            labels=("feature-request",),
        )
        == "ionos"
    )


def test_fr2512_pack_airc_alone_does_not_pin():
    # FR #1508: bare pack script edit is not an ionos pin by itself.
    assert (
        gitclaim.infer_require_machine(
            title="Pack-AircConsoleRelease script tidy",
            body="Edit Pack-Airc helpers and comments only; no MSI Apply.",
            labels=("feature-request",),
        )
        == ""
    )

def test_mrb2515_hard_pin_empty_blob_via_infer():
    """Hostile: hard pin survives totally empty title/body (stale queue row)."""
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


def test_mrb2515_offer_gap_pack_airc_cues_phrase_unpinned():
    """Hostile: receipt text 'Pack-Airc cues' must not pin (no Assert/install combo)."""
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
