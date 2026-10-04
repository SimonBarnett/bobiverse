"""FR #1899: intake/BobCallback/ARR 502 ops filings stamp require_machine=ionos."""
from __future__ import annotations

import gitclaim


def test_fr1899_1739_body_reverse_proxy_bobcallback_stamps_ionos():
    body = (
        "what: Invoke-BobiverseHarvest.ps1 -Flush got HTTP 502 from intake; "
        "payload KEPT in harvest-outbox\n"
        "fix: check irc.ntsa.uk /bob/v1/intake reverse proxy / bobcallback; "
        "operator can Flush when 502 clears."
    )
    assert (
        gitclaim.infer_require_machine(
            title="intake/harvest 502 Bad Gateway while flushing harvest-outbox",
            body=body,
            labels=("via-intake",),
        )
        == "ionos"
    )


def test_fr1899_title_intake_bobcallback_502_stamps_ionos():
    assert (
        gitclaim.infer_require_machine(
            title="chair offered intake/BobCallback 502 ops FR #1739 to flamingo without needs-ionos",
            body="labels were only via-intake",
            labels=("via-intake",),
        )
        == "ionos"
    )


def test_fr1899_bobcallback_7700_listen_stamps_ionos():
    assert (
        gitclaim.infer_require_machine(
            title="BobCallback down",
            body="no LISTEN on 127.0.0.1:7700; heal BobCallback",
            labels=("feature-request",),
        )
        == "ionos"
    )


def test_fr1899_arr_intake_stamps_ionos():
    assert (
        gitclaim.infer_require_machine(
            title="public intake 502",
            body="IIS ARR reverse proxy fronts /bob/v1/intake to BobCallback",
            labels=("via-intake",),
        )
        == "ionos"
    )


def test_fr1899_unrelated_feature_stays_ungated():
    assert (
        gitclaim.infer_require_machine(
            title="TipForm SkipTidy autostart",
            body="tray ONLOGON should use -SkipTidy so seats survive",
            labels=("feature-request",),
        )
        == ""
    )
