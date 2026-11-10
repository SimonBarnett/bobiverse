"""FR #4427 / #6407: ce-priority Day Works DEV1 auto-pin retired."""
from __future__ import annotations

import gitclaim


def test_ce_priority_day_works_living_fr_pins_dev1():
    """ce-priority#16: Day Works living FR no longer pins DEV1 (FR #6407)."""
    assert (
        gitclaim.infer_require_machine(
            title="Day Works v1.3: finish WP3-WP4 and Gates C-G per dayworks/docs/vision.md",
            body=(
                "Vision pack for CE Day Works v1.3 on Priority ERP.\n"
                "Remaining: WP3, WP4, Gates C-G.\n"
            ),
            labels=["feature-request"],
            repo="SimonBarnett/ce-priority",
            ident="#16",
        )
        == ""
    )


def test_ce_priority_day_works_uat_pins_dev1():
    assert (
        gitclaim.infer_require_machine(
            title="UAT: Day Works v1.3 Gates C-G",
            body="UAT against dayworks/docs/gates-and-uat.md on CE-PRIORITY-DEV1.",
            labels=["uat"],
            repo="SimonBarnett/ce-priority",
            ident="#0",
        )
        == ""
    )


def test_needs_ce_priority_dev1_label_pins():
    assert (
        gitclaim.infer_require_machine(
            title="Day Works follow-up",
            body="no machine name here",
            labels=["needs-ce-priority-dev1"],
            repo="SimonBarnett/ce-priority",
            ident="#99",
        )
        == ""
    )


def test_bobiverse_day_works_mention_alone_does_not_pin():
    assert (
        gitclaim.infer_require_machine(
            title=(
                "chair offered ce-priority Day Works living FR to marchhare "
                "without require_machine=ce-priority-dev1"
            ),
            body="Stamp require_machine=ce-priority-dev1 for ce-priority Day Works living FRs.",
            labels=["feature-request", "via-intake"],
            repo="SimonBarnett/bobiverse",
            ident="#4427",
        )
        == ""
    )


def test_ce_priority_unrelated_docs_fr_does_not_pin():
    assert (
        gitclaim.infer_require_machine(
            title="docs: fix typo in README",
            body="Spelling fix only.",
            labels=["feature-request"],
            repo="SimonBarnett/ce-priority",
            ident="#100",
        )
        == ""
    )


def test_hard_pin_ce_priority_16_survives_empty_body():
    assert (
        gitclaim.infer_require_machine(
            title="",
            body="",
            labels=(),
            repo="SimonBarnett/ce-priority",
            ident="#16",
        )
        == ""
    )


def test_mrb4518_hostile_fr4512_composition_keeps_dayworks_pin():
    """FR #6407: Day Works no longer pins; bobiverse meta stays empty."""
    assert (
        gitclaim.infer_require_machine(
            title="Day Works v1.3: finish WP3-WP4 and Gates C-G",
            body="Remaining living work on Priority ERP.",
            labels=["feature-request"],
            repo="SimonBarnett/ce-priority",
            ident="#16",
        )
        == ""
    )
    assert (
        gitclaim.infer_require_machine(
            title="chair offered without require_machine=ce-priority-dev1",
            body="Stamp require_machine=ce-priority-dev1 for Day Works.",
            labels=["feature-request", "via-intake"],
            repo="SimonBarnett/bobiverse",
            ident="#4427",
        )
        == ""
    )
