"""FR #8741: park-only anti-omnibus FRs are not offered until human dispatch."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

gitclaim = importlib.import_module("gitclaim")

PARK_BODY = (
    "Feature request `BOB-10`.\n\n"
    "Do not bob-job until human dispatch.\n"
    "Park: park-only (no bob-job-loop)\n"
)

DISPATCHED_BODY = (
    "Feature request `BOB-10` (dispatched).\n\n"
    "Implement Success S1 in the vision pack. Open a PR against main.\n"
)


def test_fr_park_only_reason_from_body():
    reason = gitclaim.fr_park_only_reason(title="BOB-10: About", body=PARK_BODY, labels=())
    assert reason
    assert "park-only" in reason.lower() or "bob-job" in reason.lower()


def test_fr_park_only_cleared_by_dispatched_body():
    assert (
        gitclaim.fr_park_only_reason(
            title="BOB-10: About",
            body=DISPATCHED_BODY,
            labels=(),
        )
        is None
    )


def test_fr_park_only_cleared_by_dispatch_label():
    assert (
        gitclaim.fr_park_only_reason(
            title="BOB-10: About",
            body=PARK_BODY,
            labels=("dispatched",),
        )
        is None
    )
    assert (
        gitclaim.fr_park_only_reason(
            title="BOB-10: About",
            body=PARK_BODY,
            labels=("human-dispatch",),
        )
        is None
    )


def test_fr_park_only_ignores_unrelated_body():
    assert (
        gitclaim.fr_park_only_reason(
            title="FR: tray Status dialog",
            body="Keep the Status pool usage dialog working.",
            labels=("feature-request",),
        )
        is None
    )


def test_append_unaccepted_skips_park_only(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    doc = gitclaim._empty_queue()
    claim = gitclaim.GitClaim(
        repo="SimonBarnett/bobiverse",
        task="FR",
        id="8675",
        event="issues",
        action="opened",
        line="https://github.com/SimonBarnett/bobiverse/issues/8675",
        title="BOB-10: About: Plan + Priority build versions",
        body=PARK_BODY,
        labels=("feature-request",),
    )
    changed = gitclaim._append_unaccepted(doc, claim, url=claim.line)
    assert changed == "skipped"
    assert doc["unaccepted"] == []


def test_append_unaccepted_allows_dispatched(tmp_path):
    doc = gitclaim._empty_queue()
    claim = gitclaim.GitClaim(
        repo="SimonBarnett/bobiverse",
        task="FR",
        id="8713",
        event="issues",
        action="opened",
        line="https://github.com/SimonBarnett/bobiverse/issues/8713",
        title="BOB-06: Tray menu tree",
        body=DISPATCHED_BODY,
        labels=("feature-request",),
    )
    changed = gitclaim._append_unaccepted(doc, claim, url=claim.line)
    assert changed in ("added", "updated", True) or changed != "skipped"
    assert any(str(r.get("id") or "").lstrip("#") == "8713" for r in doc["unaccepted"])


def test_append_drops_existing_when_park_appears():
    doc = gitclaim._empty_queue()
    doc["unaccepted"].append(
        {
            "repo": "SimonBarnett/bobiverse",
            "task": "FR",
            "id": "#8675",
            "url": "https://github.com/SimonBarnett/bobiverse/issues/8675",
            "title": "BOB-10",
            "body": "Goal",
            "labels": [],
        }
    )
    claim = gitclaim.GitClaim(
        repo="SimonBarnett/bobiverse",
        task="FR",
        id="8675",
        event="issues",
        action="edited",
        line="https://github.com/SimonBarnett/bobiverse/issues/8675",
        title="BOB-10",
        body=PARK_BODY,
        labels=(),
    )
    changed = gitclaim._append_unaccepted(doc, claim, url=claim.line)
    assert changed == "skipped"
    assert doc["unaccepted"] == []


def test_row_fr_skip_offer_reason_combines_hold_and_park():
    park_row = {
        "task": "FR",
        "repo": "SimonBarnett/bobiverse",
        "id": "8675",
        "title": "BOB-10",
        "body": PARK_BODY,
        "labels": [],
    }
    assert gitclaim.row_fr_park_only_reason(park_row)
    assert gitclaim.row_fr_skip_offer_reason(park_row)
    hold_row = {
        "task": "FR",
        "repo": "SimonBarnett/bobiverse",
        "id": "3991",
        "title": "FR: installer",
        "labels": ["hold"],
    }
    assert gitclaim.row_fr_skip_offer_reason(hold_row)
    clear_row = {
        "task": "FR",
        "body": DISPATCHED_BODY,
        "labels": [],
        "title": "BOB-06",
    }
    assert gitclaim.row_fr_skip_offer_reason(clear_row) is None
