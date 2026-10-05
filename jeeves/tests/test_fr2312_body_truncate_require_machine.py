"""FR #2312: queue body[:500] must not drop trailing require_machine: ionos pins."""
from __future__ import annotations

import re
import sys
from pathlib import Path

from repo_layout import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import gitclaim  # noqa: E402


def _long_body_with_trailing_pin() -> str:
    # Mirrors #1714: pin after a long Ask/Evidence/Fix block (past 500 chars).
    head = (
        "## Ask\n"
        "`clear_orphan_digest_mrb_doing` / DONE idle path must clear both worker_list "
        "and workers map plus machine-level working_on. " * 8
        + "\n## Evidence\n- win-mpre DONE then nak busy\n## Fix\n1. clear workers map\n"
        "2. worker_working_on heal\n## Do not\n- Stamp needs-mrb1\n- Restart BobIrcd\n\n"
    )
    assert len(head) > 500
    return head + "require_machine: ionos\n"


def _has_ionos_pin(text: str) -> bool:
    return bool(re.search(r"(?im)^\s*require_machine\s*[:=]\s*ionos\b", text))


def test_fr2312_body_for_queue_preserves_trailing_ionos_pin():
    full = _long_body_with_trailing_pin()
    assert "require_machine: ionos" not in full[:500]
    stored = gitclaim._body_for_queue(full)
    assert _has_ionos_pin(stored)
    # Use a non-hard-pinned id so inference must come from preserved body text.
    mid = gitclaim.infer_require_machine(
        title="FR: clear workers map on orphan MRB DONE",
        body=stored,
        labels=["feature-request", "via-intake"],
        repo="SimonBarnett/bobiverse",
        ident="#999901",
    )
    assert mid == "ionos"


def test_fr2312_append_unaccepted_stamps_and_preserves_pin():
    doc = {"unaccepted": [], "accepted": [], "done": []}
    body = _long_body_with_trailing_pin()
    claim = gitclaim.GitClaim(
        repo="SimonBarnett/bobiverse",
        task="FR",
        id="#999902",
        event="issues",
        action="opened",
        line="",
        title="FR: clear workers map + machine working_on on orphan MRB DONE",
        body=body,
        labels=["feature-request", "via-intake"],
        state="open",
    )
    assert gitclaim._append_unaccepted(doc, claim) == "added"
    row = doc["unaccepted"][0]
    assert row.get("require_machine") == "ionos"
    assert _has_ionos_pin(str(row.get("body") or ""))
    assert gitclaim.row_blocked_for_machine(row, "marchhare-35016") is True
    # FR #2525: parse_seat_nick only accepts machines in seat_machine_ids(); pin the
    # canonical fold target so ionos↔win-mpre matching is not digest-environment flake.
    import bobreport

    real_ids = bobreport.seat_machine_ids

    def _ids():
        return set(real_ids()) | {"win-mpre8vi4u6u", "ionos"}

    bobreport.seat_machine_ids = _ids  # type: ignore[assignment]
    try:
        assert gitclaim.row_blocked_for_machine(row, "win-mpre8vi4u6u-1") is False
        assert gitclaim.row_blocked_for_machine(row, "ionos-1") is False
    finally:
        bobreport.seat_machine_ids = real_ids  # type: ignore[assignment]


def test_fr2312_naive_truncate_would_miss_pin_but_helper_does_not():
    full = _long_body_with_trailing_pin()
    naive = full[:500]
    assert (
        gitclaim.infer_require_machine(
            title="FR: clear workers map",
            body=naive,
            labels=["feature-request", "via-intake"],
            repo="SimonBarnett/bobiverse",
            ident="#999903",
        )
        == ""
    )
    assert (
        gitclaim.infer_require_machine(
            title="FR: clear workers map",
            body=gitclaim._body_for_queue(full),
            labels=["feature-request", "via-intake"],
            repo="SimonBarnett/bobiverse",
            ident="#999903",
        )
        == "ionos"
    )


def test_fr2312_issue_pin_1714_belt_and_suspenders():
    # Even with empty body/labels, known ionos orphan-DONE FR stays pinned.
    mid = gitclaim.infer_require_machine(
        title="",
        body="",
        labels=[],
        repo="SimonBarnett/bobiverse",
        ident="#1714",
    )
    assert mid == "ionos"
    row = {
        "repo": "SimonBarnett/bobiverse",
        "id": "#1714",
        "task": "FR",
        "title": "FR: clear workers map",
        "body": "",
        "labels": ["feature-request", "via-intake"],
    }
    assert gitclaim.row_blocked_for_machine(row, "marchhare-35016") is True
