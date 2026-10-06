"""Hostile MRB #2468: install(+smoke) on ionos pins; bare release-out / bare ionos evidence do not."""
from __future__ import annotations

import gitclaim
from repo_layout import ROOT


def test_hostile_smoke_on_ionos_body_pins():
    assert (
        gitclaim.infer_require_machine(
            title="release: pack bob MSI",
            body="After Assert-ReleaseAssets, smoke on ionos briefly.",
            labels=("feature-request",),
        )
        == "ionos"
    )


def test_hostile_on_ionos_without_install_smoke_does_not_pin():
    assert (
        gitclaim.infer_require_machine(
            title="docs: note about ionos chair",
            body="Discussed on ionos after the release pack; no install step.",
            labels=("feature-request",),
        )
        == ""
    )


def test_hostile_marchhare_blocked_when_pinned_ionos():
    pin = gitclaim.infer_require_machine(
        title="release pack: install on ionos",
        body="acceptance: install on ionos",
        labels=("feature-request",),
    )
    assert pin == "ionos"
    # Legacy short nicks parse without a digest roster (DIGEST_ID_FOLD ionos→win-mpre*).
    assert gitclaim.seat_matches_require_machine("w-mh-1", pin) is False
    assert gitclaim.seat_matches_require_machine("w-io-7764", pin) is True


def test_hostile_source_mentions_2451():
    src = (ROOT / "common" / "scripts" / "gitclaim.py").read_text(encoding="utf-8")
    assert "FR #2451" in src
    assert r"install(?:\s*\+\s*smoke|\+smoke)?\s+on\s+ionos" in src
