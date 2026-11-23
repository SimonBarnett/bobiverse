"""FR #9395: PR title prose 'on hold' (VIS-G1 create digest) must not skip MRB."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))
gitclaim = importlib.import_module("gitclaim")


def test_fr9395_vis_g1_title_on_hold_prose_not_hold():
    reason = gitclaim.pr_hold_reason(
        title="VIS-G1 / FR #155: Create fr-digest on hold before children",
        body=(
            "At batch park, create the fr-digest + hold digest issue before any child FR.\n"
            "Labels fr-digest+hold at create are issues-only.\n"
        ),
        labels=(),
    )
    assert reason is None


def test_fr9395_title_on_hold_colon_still_holds():
    reason = gitclaim.pr_hold_reason(
        title="On hold: wait for Si before merge",
        body="",
        labels=(),
    )
    assert reason
    assert "hold" in reason.lower()


def test_fr9395_title_leading_on_hold_still_holds():
    reason = gitclaim.pr_hold_reason(
        title="On hold until digest unholds",
        body="",
        labels=(),
    )
    assert reason


def test_fr9395_body_owner_stamp_still_holds():
    reason = gitclaim.pr_hold_reason(
        title="VIS-G1 create fr-digest on hold",
        body="On hold (Simon): must not merge until gate closes.\n",
        labels=(),
    )
    assert reason
    assert "hold" in reason.lower()