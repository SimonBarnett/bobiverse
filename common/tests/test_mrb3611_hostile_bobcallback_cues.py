"""Hostile pins for MRB #3611 / FR #3610 BobCallback require_machine cues."""
from __future__ import annotations

from pathlib import Path

import gitclaim
from repo_layout import ROOT


def test_mrb3611_design_prose_7700_stays_ungated():
    assert (
        gitclaim.infer_require_machine(
            title="FR: Hours webhook",
            body="BobCallback (default 127.0.0.1:7700) stores hours under digest home.",
            labels=("feature-request",),
        )
        == ""
    )


def test_mrb3611_reverse_restart_stamps_ionos():
    """FR #3610 lists restart/recycle; reverse adjacency must match forward."""
    assert (
        gitclaim.infer_require_machine(
            title="heal callback",
            body="please restart BobCallback on the chair host after the wedge",
            labels=("via-intake",),
        )
        == "ionos"
    )


def test_mrb3611_reverse_recycle_stamps_ionos():
    assert (
        gitclaim.infer_require_machine(
            title="heal callback",
            body="recycle BobCallback after IIS rewrite landed",
            labels=("via-intake",),
        )
        == "ionos"
    )


def test_mrb3611_bare_listen_word_without_outage_stays_ungated():
    assert (
        gitclaim.infer_require_machine(
            title="FR: document listen assumption",
            body="BobCallback LISTEN on the existing port is already assumed for hours.",
            labels=("feature-request",),
        )
        == ""
    )


def test_mrb3611_monitor_skill_cites_fr3610_contiguous():
    text = (
        ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-monitor" / "SKILL.md"
    ).read_text(encoding="utf-8")
    needle = (
        "**FR #3610:** BobCallback body cues need outage/ops wording "
        "(DOWN, 502, Bad Gateway, no LISTEN, restart/recycle)"
    )
    assert needle in text
    assert "Hours webhook FR #3450" in text
