"""FR #3610: BobCallback design prose must not stamp require_machine=ionos."""
from __future__ import annotations

import gitclaim

# Fixture: Hours webhook FR #3450 body snippet that previously matched
# BobCallback ... :7700 and hid the FR from MarchHare seats.
_FR3450_BODY = """
## Where it lives (existing code)

The fleet digest webhook is BobCallback (default `127.0.0.1:7700`, public front door
`https://irc.ntsa.uk/bob/v1/report`):

- `common/scripts/bobcallback.py`: route constants (`REPORT_PATH`, `INTAKE_PATH`), `serve()`.
- Agents POST partial time entries; Haitch GETs them to draft Priority hours.

## Shape

service / webhook route under BobCallback. LISTEN on the existing port is already assumed.
"""


def test_fr3610_hours_webhook_design_prose_stays_ungated():
    assert (
        gitclaim.infer_require_machine(
            title=(
                "FR: Hours webhook — let agents record partial work-time entries "
                "as source material for timesheets"
            ),
            body=_FR3450_BODY,
            labels=("feature-request",),
        )
        == ""
    )


def test_fr3610_bobcallback_port_only_stays_ungated():
    assert (
        gitclaim.infer_require_machine(
            title="FR: document BobCallback bind address",
            body="BobCallback binds 127.0.0.1:7700 for local digest posts; no outage.",
            labels=("feature-request",),
        )
        == ""
    )


def test_fr3610_outage_down_still_stamps_ionos():
    assert (
        gitclaim.infer_require_machine(
            title="BobCallback DOWN ~30m",
            body="BobCallback DOWN; heal and restart on ionos",
            labels=("via-intake",),
        )
        == "ionos"
    )


def test_fr3610_outage_502_still_stamps_ionos():
    assert (
        gitclaim.infer_require_machine(
            title="intake 502",
            body="HTTP 502 Bad Gateway from BobCallback while flushing harvest-outbox",
            labels=("via-intake",),
        )
        == "ionos"
    )


def test_fr3610_no_listen_heal_still_stamps_ionos():
    """Keep FR #1899 outage fixture: no LISTEN + BobCallback heal."""
    assert (
        gitclaim.infer_require_machine(
            title="BobCallback down",
            body="no LISTEN on 127.0.0.1:7700; heal BobCallback",
            labels=("feature-request",),
        )
        == "ionos"
    )
