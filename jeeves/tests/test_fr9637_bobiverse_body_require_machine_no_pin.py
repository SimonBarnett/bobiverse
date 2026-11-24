"""FR #9637: bobiverse body require_machine: alone must not pin (idle starve).

Monitor filings pasted ``require_machine: walrus`` into implement-anywhere chair
FRs; chair stamped the queue and offerable dropped to 0 until ``!unpin``.
Pins require ``needs-<machine>`` / ``require_machine:<machine>`` labels, hard
issue pins, or operator ``!pin``.
"""
from __future__ import annotations

import gitclaim


def test_fr9637_monitor_walrus_body_line_does_not_pin():
    mid = gitclaim.infer_require_machine(
        title="chair: sticky offered + NAK !BORED busy while digest idle",
        body=(
            "## Fix (ircJeeves)\n"
            "1. On !bored while sticky-offered...\n\n"
            "require_machine: walrus\n"
            "Refs: #9628 #9627\n"
        ),
        labels=["feature-request", "via-intake"],
        repo="SimonBarnett/bobiverse",
        ident="#9633",
    )
    assert mid == ""


def test_fr9637_needs_walrus_label_still_pins():
    mid = gitclaim.infer_require_machine(
        title="chair: sticky offered + NAK !BORED busy while digest idle",
        body="require_machine: walrus\n",
        labels=["feature-request", "needs-walrus"],
        repo="SimonBarnett/bobiverse",
        ident="#9633",
    )
    assert mid == "walrus"


def test_fr9637_stamp_clears_body_only_walrus():
    row = {
        "repo": "SimonBarnett/bobiverse",
        "id": "9633",
        "task": "FR",
        "title": "chair sticky offered NAK",
        "body": "require_machine: walrus\n",
        "labels": ["via-intake", "feature-request"],
        "require_machine": "walrus",
    }
    gitclaim._stamp_require_machine(row)
    stamped = str(row.get("require_machine") or "").strip().lower()
    assert stamped in {"", "any", "none", "*", "-"}
    assert gitclaim.row_require_machine(row) == ""
