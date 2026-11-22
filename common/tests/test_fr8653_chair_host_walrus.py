"""FR #8653: chair-host cues offer on walrus. Legacy ionos pins fold there."""
from __future__ import annotations

import gitclaim


def test_needs_walrus_and_legacy_ionos_pin_to_walrus():
    assert (
        gitclaim.infer_require_machine(
            title="Sync ircJeeves allowlist",
            body="require_machine: walrus\n",
            repo="SimonBarnett/bobiverse",
        )
        == "walrus"
    )
    assert (
        gitclaim.infer_require_machine(
            title="old pin",
            body="require_machine: ionos\n",
            repo="SimonBarnett/bobiverse",
        )
        == "walrus"
    )
    assert (
        gitclaim.infer_require_machine(
            title="needs-walrus chair compose",
            labels=("needs-walrus",),
            repo="SimonBarnett/other",
        )
        == "walrus"
    )
    assert (
        gitclaim.infer_require_machine(
            title="needs-ionos chair compose",
            labels=("needs-ionos",),
            repo="SimonBarnett/other",
        )
        == "walrus"
    )


def test_legacy_ionos_stamp_matches_walrus_seat(monkeypatch):
    import bobreport

    monkeypatch.setattr(bobreport, "seat_machine_ids", lambda: ("walrus", "marchhare", "ionos"))
    assert gitclaim.seat_matches_require_machine("walrus-4", "ionos") is True
    assert gitclaim.seat_matches_require_machine("ionos-4", "walrus") is True
    assert gitclaim.seat_matches_require_machine("ionos-4", "ionos") is True
    assert gitclaim.seat_matches_require_machine("marchhare-4", "ionos") is False
    assert gitclaim.fold_chair_host("ionos") == "walrus"
    assert gitclaim.fold_chair_host("flamingo") == "flamingo"
    # FR #8697: digest alias fold agrees with chair-host fold (not win-mpre).
    assert bobreport.DIGEST_ID_FOLD.get("ionos") == "walrus"
    assert bobreport.fold_machine_id("ionos") == "walrus"
    assert bobreport.NICK_TO_MACHINE.get("bob-ionos") == "walrus"
