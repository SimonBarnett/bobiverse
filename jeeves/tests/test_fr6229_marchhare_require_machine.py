"""FR #6229: stamp require_machine=marchhare for live MarchHare gate #6144."""
from __future__ import annotations

import sys

from repo_layout import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import gitclaim  # noqa: E402


def test_fr6229_hard_pin_bobiverse_6144():
    assert (
        gitclaim.infer_require_machine(
            title="FR-004: MarchHare pool remaining/reset correctness",
            body="short body without dedicated pin line",
            labels=("feature-request",),
            repo="SimonBarnett/bobiverse",
            ident="6144",
        )
        == "marchhare"
    )
    assert (
        gitclaim.infer_require_machine(
            title="FR-004",
            body="",
            labels=(),
            repo="SimonBarnett/bobiverse",
            ident="#6144",
        )
        == "marchhare"
    )


def test_fr6229_offer_gap_meta_does_not_self_pin():
    """Offer-gap filing about #6144 must stay offerable on any shop (FR #4422-class)."""
    assert (
        gitclaim.infer_require_machine(
            title="offer-gap: FR #6144 live MarchHare gate offered to redqueen",
            body=(
                "Jeeves offered FR #6144 to redqueen. Owner gate needs live MarchHare.\n"
                "Stamp require_machine=marchhare so non-MarchHare seats are not offered."
            ),
            labels=("via-intake",),
            repo="SimonBarnett/bobiverse",
            ident="#6229",
        )
        == ""
    )


def test_fr6229_needs_marchhare_label_pins():
    assert (
        gitclaim.infer_require_machine(
            title="unrelated title",
            body="no dedicated line",
            labels=("needs-marchhare",),
            repo="SimonBarnett/bobiverse",
            ident="#99999",
        )
        == "marchhare"
    )
    assert (
        gitclaim.infer_require_machine(
            title="unrelated",
            body="",
            labels=("machine:marchhare",),
            repo="SimonBarnett/other",
            ident="#1",
        )
        == "marchhare"
    )


def test_fr6229_dedicated_body_line_still_pins_bobiverse():
    assert (
        gitclaim.infer_require_machine(
            title="ops",
            body="require_machine: marchhare\n\nLive tray proof.",
            labels=("feature-request",),
            repo="SimonBarnett/bobiverse",
            ident="#99998",
        )
        == "marchhare"
    )


def test_fr6229_stamp_persists_on_6144_row():
    row = {
        "repo": "SimonBarnett/bobiverse",
        "id": "#6144",
        "title": "FR-004: MarchHare pool",
        "body": "short",
        "require_machine": "",
    }
    gitclaim._stamp_require_machine(row)
    assert row["require_machine"] == "marchhare"


def test_fr6229_soft_marchhare_prose_does_not_pin_bobiverse():
    """FR #4512: bobiverse soft text never pins; only hard pin / label / dedicated line."""
    assert (
        gitclaim.infer_require_machine(
            title="docs: MarchHare digest clocks",
            body="Live MarchHare source to digest to tray validation notes.",
            labels=("via-intake",),
            repo="SimonBarnett/bobiverse",
            ident="#99997",
        )
        == ""
    )
