"""FR #1550: monitor idle+ungated / ircJeeves StartPending filings pin require_machine=ionos."""
from __future__ import annotations

import gitclaim


def test_fr1550_title_idle_ungated_after_startpending_pins_ionos():
    mid = gitclaim.infer_require_machine(
        title="idle seats + ungated offerable #1545/#1546/#1547 after ircJeeves StartPending",
        body="",
    )
    assert mid == "ionos"


def test_fr1550_title_startpending_ircjeeves_either_order():
    assert (
        gitclaim.infer_require_machine(
            title="ircJeeves StartPending left seats idle",
            body="",
        )
        == "ionos"
    )
    assert (
        gitclaim.infer_require_machine(
            title="StartPending on ircJeeves after recycle",
            body="",
        )
        == "ionos"
    )


def test_fr1550_body_monitor_check_and_no_shop_offer_pin_ionos():
    assert (
        gitclaim.infer_require_machine(
            title="FR: seats idle after chair flap",
            body="Invoke-JeevesMonitorCheck -Check idle_seats showed ungated_offerable>0",
        )
        == "ionos"
    )
    assert (
        gitclaim.infer_require_machine(
            title="FR: keep the flow",
            body="chair-outbox has GIT announces but no shop OFFER lines to #marchhare",
        )
        == "ionos"
    )


def test_fr1550_does_not_pin_unrelated_idle_prose():
    # Bare "idle seats" without ungated/StartPending must not steal marchhare work.
    assert (
        gitclaim.infer_require_machine(
            title="FR: tip tray shows idle seats count",
            body="cosmetic UI for idle seats meter on TipForm",
        )
        == ""
    )


def test_fr1550_body_mention_of_dev1_pin_still_not_repin_from_bare_machine():
    # FR #1508 regression: evidence about DEV1 pins in body must not re-pin.
    mid = gitclaim.infer_require_machine(
        title="FR: monitor report shape",
        body="Pins #56/#1102 remain ce-priority-dev1-only; ungated were #1545.",
    )
    # Title has no StartPending/idle+ungated; body has Invoke? no — only DEV1 mention.
    assert mid == ""
