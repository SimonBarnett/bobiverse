"""FR #3129: Sync/compose ircJeeves + Sync-BobiverseFromRepo must pin require_machine=ionos."""
from __future__ import annotations

import sys
from pathlib import Path

from repo_layout import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import gitclaim  # noqa: E402


def test_fr3129_title_ionos_sync_compose_ircjeeves_pins():
    mid = gitclaim.infer_require_machine(
        title="ionos Sync/compose ircJeeves — intake allowlist a-search/trutex still 403",
        body="Confirm live probe returns non-403.",
        labels=["feature-request", "via-intake"],
        repo="SimonBarnett/bobiverse",
        ident="#3122",
    )
    assert mid == "ionos"


def test_fr3129_body_sync_bobiverse_from_repo_pins():
    mid = gitclaim.infer_require_machine(
        title="intake allowlist drift",
        body=(
            "## Fix\n"
            "On ionos: Sync-BobiverseFromRepo (or restart ircJeeves so start-time "
            "ff+compose picks up main). Do not touch BobIrcd/Ergo.\n"
        ),
        labels=["feature-request"],
        repo="SimonBarnett/bobiverse",
        ident="#9999",
    )
    assert mid == "ionos"


def test_fr3129_hard_pin_issue_3122():
    mid = gitclaim.infer_require_machine(
        title="",
        body="",
        labels=[],
        repo="SimonBarnett/bobiverse",
        ident="#3122",
    )
    assert mid == "ionos"


def test_fr3129_offer_gap_issue_itself_not_forced_ionos_without_cues():
    """#3129 is a code FR (gitclaim cues) — may run on any seat."""
    mid = gitclaim.infer_require_machine(
        title="chair offered ionos Sync FR #3122 to marchhare",
        body=(
            "Stamp require_machine=ionos so non-ionos seats never receive the offer.\n"
            "Evidence: Worker GIVEUP require_machine=ionos.\n"
        ),
        labels=["via-intake"],
        repo="SimonBarnett/bobiverse",
        ident="#3129",
    )
    # Inline evidence require_machine= must not pin (#1824); title lacks jeeves/compose pair.
    assert mid == ""


def test_fr3129_bare_sync_bobiverse_from_repo_does_not_pin():
    """bob/airc Sync-BobiverseFromRepo on any fleet box must not force ionos."""
    mid = gitclaim.infer_require_machine(
        title="hotpatch bob ear then sync",
        body="Run Sync-BobiverseFromRepo -Product bob on marchhare after hotpatch.",
        labels=["feature-request"],
        repo="SimonBarnett/bobiverse",
        ident="#9997",
    )
    assert mid == ""


def test_fr3129_sync_bobiverse_near_jeeves_still_pins():
    mid = gitclaim.infer_require_machine(
        title="stale intake allowlist",
        body="Sync-BobiverseFromRepo then restart ircJeeves so compose picks up main.",
        labels=["feature-request"],
        repo="SimonBarnett/bobiverse",
        ident="#9996",
    )
    assert mid == "ionos"
