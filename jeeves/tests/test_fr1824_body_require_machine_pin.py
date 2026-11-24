"""FR #1824 / #1843: explicit body-line require_machine: ionos must pin (not evidence prose)."""
from __future__ import annotations

import sys
from pathlib import Path

from repo_layout import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import gitclaim  # noqa: E402


def test_fr1824_body_line_require_machine_colon_ionos_no_longer_pins():
    # FR #9637: bobiverse body require_machine: alone does not pin (needs label / !pin).
    mid = gitclaim.infer_require_machine(
        title="FR: clear workers map + machine working_on on orphan MRB DONE",
        body=(
            "what: clear orphan digest after lost DONE\n"
            "where: ionos chair\n"
            "fix: clear workers.*.working_on\n"
            "require_machine: ionos\n"
        ),
        labels=["feature-request", "via-intake"],
        repo="SimonBarnett/bobiverse",
        ident="#9991714",
    )
    assert mid == ""


def test_fr1824_needs_walrus_label_still_pins():
    mid = gitclaim.infer_require_machine(
        title="FR: clear workers map + machine working_on on orphan MRB DONE",
        body="require_machine: ionos\n",
        labels=["feature-request", "needs-walrus"],
        repo="SimonBarnett/bobiverse",
        ident="#9991714",
    )
    assert mid == "walrus"


def test_fr1824_body_line_require_machine_equals_ionos_no_longer_pins():
    mid = gitclaim.infer_require_machine(
        title="chair offered ionos-pinned FR to wrong shop",
        body="evidence...\n\nrequire_machine=ionos\n",
        labels=["via-intake"],
        repo="SimonBarnett/bobiverse",
        ident="#1687",
    )
    assert mid == ""


def test_fr1508_inline_evidence_require_machine_still_does_not_pin():
    mid = gitclaim.infer_require_machine(
        title="FR: bobiverse seats idle — prune closed focus",
        body=(
            "Evidence: queue only has require_machine=ce-priority-dev1 pins "
            "while ce-priority-dev1 has zero seats."
        ),
        labels=["feature-request", "via-intake"],
        repo="SimonBarnett/bobiverse",
        ident="#1508",
    )
    assert mid == ""
