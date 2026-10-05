"""FR #2525: backtick / trailing-note require_machine pin lines + hard-pin #2522."""
from __future__ import annotations

import re

import gitclaim

_FR2522_TITLE = (
    "FR: Jeeves maintenance agent — butler icon, resume, self-exit+harvest, "
    "extensible self-test checks"
)
# Trailing pin as filed (past QUEUE_BODY_LIMIT) with markdown backticks + note.
_FR2522_TAIL = "`require_machine: ionos` (hotpatch verify)\n"


def _long_body_backtick_pin() -> str:
    head = (
        "## What\nHarden the Jeeves maintenance agent. " * 20
        + "\n## Acceptance\n- Title + butler icon\n- Resume helper\n\n"
    )
    assert len(head) > 500
    return head + _FR2522_TAIL


def test_fr2525_hard_pin_2522_empty_blob():
    assert (
        gitclaim.infer_require_machine(
            title="",
            body="",
            labels=(),
            repo="SimonBarnett/bobiverse",
            ident="#2522",
        )
        == "ionos"
    )


def test_fr2525_body_for_queue_preserves_backtick_pin():
    full = _long_body_backtick_pin()
    assert "require_machine" not in full[:500]
    stored = gitclaim._body_for_queue(full)
    assert re.search(r"(?im)require_machine\s*[:=]\s*ionos\b", stored)
    mid = gitclaim.infer_require_machine(
        title=_FR2522_TITLE,
        body=stored,
        labels=["feature-request"],
        repo="SimonBarnett/bobiverse",
        ident="#999925",
    )
    assert mid == "ionos"


def test_fr2525_infer_backtick_line_with_trailing_note():
    assert (
        gitclaim.infer_require_machine(
            title="maintenance butler",
            body="Relates #2412\n\n`require_machine: ionos` (hotpatch verify)\n",
            labels=["feature-request"],
        )
        == "ionos"
    )


def test_fr2525_offer_gap_receipt_unpinned():
    assert (
        gitclaim.infer_require_machine(
            title="chair offered ionos-pinned maintenance FR #2522 to marchhare",
            body="fix: stamp require_machine=ionos from dedicated body line; refs #2522",
            labels=["via-intake"],
            repo="SimonBarnett/bobiverse",
            ident="#2525",
        )
        == ""
    )


def test_fr2525_append_unaccepted_stamps_2522_shaped(tmp_path=None):
    doc = {"unaccepted": [], "accepted": [], "done": []}
    body = _long_body_backtick_pin()
    claim = gitclaim.GitClaim(
        repo="SimonBarnett/bobiverse",
        task="FR",
        id="#999926",
        event="issues",
        action="opened",
        line="",
        title=_FR2522_TITLE,
        body=body,
        labels=["feature-request"],
        state="open",
    )
    assert gitclaim._append_unaccepted(doc, claim) == "added"
    row = doc["unaccepted"][0]
    assert row.get("require_machine") == "ionos"
    assert "require_machine: ionos" in str(row.get("body") or "")
    assert gitclaim.row_blocked_for_machine(row, "marchhare-40208") is True
