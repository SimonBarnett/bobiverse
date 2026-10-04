"""FR #1559: pin ionos for ircJeeves StartPending / chair-outbox monitor findings."""
from __future__ import annotations

import gitclaim


def test_title_ircjeeves_startpending_pins_ionos():
    mid = gitclaim.infer_require_machine(
        title="idle seats + ungated offerable after ircJeeves StartPending",
        body="",
        labels=["via-intake"],
        repo="SimonBarnett/bobiverse",
        ident="#1550",
    )
    assert mid == "ionos"


def test_body_ircjeeves_equals_startpending_pins_ionos():
    mid = gitclaim.infer_require_machine(
        title="monitor: idle seats while ungated offerable",
        body="health briefly `ircJeeves=StartPending` then recovered to Running",
        labels=["via-intake"],
    )
    assert mid == "ionos"


def test_issue1550_shaped_blob_pins_ionos():
    """Real #1550: recycle→ircJeeves is >60 chars so FR #852 cue misses; StartPending must pin."""
    title = "idle seats + ungated offerable #1545/#1546/#1547 after ircJeeves StartPending"
    body = (
        "## What\n"
        "Monitor idle_seats exit 1 after chair recycle: **8 idle seats** with "
        "**3 ungated offerable** FRs while offerable_for_live_seats>0.\n\n"
        "## Evidence\n"
        "- health briefly `ircJeeves=StartPending` then recovered to **Running** "
        "(pid 5072); did not Restart-Service (not Stopped).\n"
        "- `Invoke-JeevesMonitorCheck -Check idle_seats` → findings.\n"
    )
    mid = gitclaim.infer_require_machine(
        title=title,
        body=body,
        labels=["via-intake"],
        repo="SimonBarnett/bobiverse",
        ident="#1550",
    )
    assert mid == "ionos"


def test_body_chair_outbox_with_idle_seats_pins_ionos():
    mid = gitclaim.infer_require_machine(
        title="monitor finding",
        body="chair-outbox evidence: idle_seats with offerable rows after recycle",
        labels=["via-intake"],
    )
    assert mid == "ionos"


def test_body_chair_outbox_alone_does_not_pin():
    """FR #1508: bare body mentions must not re-pin; chair-outbox stays title-strong only unless paired."""
    mid = gitclaim.infer_require_machine(
        title="monitor finding",
        body="see the chair-outbox log for prior lines",
        labels=["via-intake"],
    )
    assert mid == ""


def test_title_chair_outbox_still_pins():
    mid = gitclaim.infer_require_machine(
        title="chair-outbox delay after recycle",
        body="",
        labels=["via-intake"],
    )
    assert mid == "ionos"


def test_invoke_jeeves_monitor_idle_seats_pins_ionos():
    mid = gitclaim.infer_require_machine(
        title="fleet monitor alert",
        body="Invoke-JeevesMonitorCheck -Check idle_seats returned exit 1",
        labels=["via-intake"],
    )
    assert mid == "ionos"


def test_bare_ionos_in_body_still_does_not_pin():
    mid = gitclaim.infer_require_machine(
        title="FR: seats idle",
        body="Evidence mentions ionos only as the chair host name in a screenshot.",
        labels=["feature-request"],
    )
    assert mid == ""
