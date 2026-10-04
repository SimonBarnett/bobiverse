"""MRB #2319 hostile coverage for queue body truncate + require_machine pin survival."""
from __future__ import annotations

import re
import sys

from repo_layout import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import gitclaim  # noqa: E402


def _pad(n: int, fill: str = "x") -> str:
    return fill * n


def _has_pin(text: str, machine: str = "ionos") -> bool:
    return bool(
        re.search(
            rf"(?im)^\s*require_machine\s*[:=]\s*{re.escape(machine)}\b",
            text,
        )
    )


def test_mrb2319_equals_form_pin_past_limit():
    head = _pad(520) + "\n"
    full = head + "require_machine = ionos\n"
    assert "require_machine" not in full[:500]
    stored = gitclaim._body_for_queue(full)
    assert _has_pin(stored)
    assert (
        gitclaim.infer_require_machine(
            title="ops",
            body=stored,
            labels=["feature-request"],
            repo="SimonBarnett/bobiverse",
            ident="#999911",
        )
        == "ionos"
    )


def test_mrb2319_pin_already_in_head_not_duplicated():
    pin = "require_machine: ionos"
    full = pin + "\n" + _pad(600)
    stored = gitclaim._body_for_queue(full)
    assert stored.count(pin) == 1
    assert stored == full[: gitclaim.QUEUE_BODY_LIMIT].rstrip()


def test_mrb2319_blank_line_before_trailing_pin():
    full = _pad(510) + "\n\nrequire_machine: ionos\n"
    stored = gitclaim._body_for_queue(full)
    assert _has_pin(stored)
    # Stamp path with claim=None must still infer from preserved stored body.
    row = {
        "repo": "SimonBarnett/bobiverse",
        "id": "#999912",
        "task": "FR",
        "title": "FR: trailing pin",
        "body": stored,
        "labels": ["feature-request", "via-intake"],
    }
    gitclaim._stamp_require_machine(row, None)
    assert row.get("require_machine") == "ionos"
    assert gitclaim.row_blocked_for_machine(row, "marchhare-1") is True
    assert gitclaim.row_blocked_for_machine(row, "win-mpre8vi4u6u-9") is False


def test_mrb2319_ce_priority_trailing_pin():
    full = _pad(505) + "\nrequire_machine: ce-priority-dev1\n"
    stored = gitclaim._body_for_queue(full)
    assert _has_pin(stored, "ce-priority-dev1")
    assert (
        gitclaim.infer_require_machine(
            title="",
            body=stored,
            labels=[],
            repo="SimonBarnett/other",
            ident="#1",
        )
        == "ce-priority-dev1"
    )


def test_mrb2319_short_body_unchanged():
    body = "short\nrequire_machine: ionos\n"
    assert gitclaim._body_for_queue(body) == body


def test_mrb2319_limit_edge_uses_default_when_nonpositive():
    full = _pad(520) + "\nrequire_machine: ionos\n"
    stored = gitclaim._body_for_queue(full, limit=0)
    assert _has_pin(stored)
    assert len(stored) <= gitclaim.QUEUE_BODY_LIMIT + 40


def test_mrb2319_naive_truncate_loses_stamp_on_row_only_refresh():
    """Defense: without helper, a later stamp from row.body alone would clear the gate."""
    full = _pad(520) + "\nrequire_machine: ionos\n"
    naive = full[:500]
    row = {
        "repo": "SimonBarnett/bobiverse",
        "id": "#999913",
        "task": "FR",
        "title": "FR: truncate loss",
        "body": naive,
        "labels": ["feature-request"],
    }
    gitclaim._stamp_require_machine(row, None)
    assert not row.get("require_machine")
    row["body"] = gitclaim._body_for_queue(full)
    gitclaim._stamp_require_machine(row, None)
    assert row.get("require_machine") == "ionos"