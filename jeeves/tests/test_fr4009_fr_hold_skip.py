"""FR #4009: label:hold / owner HOLD body stamp must not enqueue or offer FR rows.

Mirrors FR #3928 (PR hold) for issues. Does not put ``hold`` in SKIP_FR_LABELS so
held product FRs can still block repo UAT until closed or cleared.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

gitclaim = importlib.import_module("gitclaim")

HOLD_BODY = (
    "**HOLD (2026-10-11, Simon):** Do not start until v0.1.31 (or a later release) "
    "has an airc MSI that installs cleanly. Bob will add the `feature-request` "
    "label when released.\n\n## Goal\n\nShip airc-network-installer.exe."
)


def test_fr_hold_reason_from_hold_label():
    assert gitclaim.fr_hold_reason(title="FR: network installer", body="", labels=("hold",))
    assert gitclaim.fr_hold_reason(title="FR: x", body="", labels=("on-hold",))
    assert gitclaim.fr_hold_reason(title="FR: x", body="", labels=("feature-request",)) is None


def test_fr_hold_reason_from_owner_hold_body_stamp():
    reason = gitclaim.fr_hold_reason(
        title="FR: airc-network-installer.exe",
        body=HOLD_BODY,
        labels=(),
    )
    assert reason
    assert "hold" in reason.lower()


def test_fr_hold_reason_ignores_prose_hold_word():
    body = (
        "Acceptance: the install must hold the previous version when --dry-run. "
        "Do not put the password in argv."
    )
    assert (
        gitclaim.fr_hold_reason(
            title="FR: network installer",
            body=body,
            labels=(),
        )
        is None
    )


def test_hold_not_in_skip_fr_labels_keeps_uat_block():
    """hold is offer-gated via fr_hold_reason, not SKIP_FR (UAT still sees open FR)."""
    assert "hold" not in gitclaim.SKIP_FR_LABELS
    assert "on-hold" not in gitclaim.SKIP_FR_LABELS
    assert (
        gitclaim.issue_skip_fr_reason(
            title="FR: airc-network-installer",
            body=HOLD_BODY,
            labels=("hold",),
        )
        is None
    )
    assert gitclaim.issue_blocks_repo_uat(
        title="FR: airc-network-installer",
        body=HOLD_BODY,
        labels=("hold",),
    )


def test_append_unaccepted_skips_fr_when_hold_label(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    doc = gitclaim._empty_queue()
    claim = gitclaim.GitClaim(
        repo="SimonBarnett/bobiverse",
        task="FR",
        id="3991",
        event="issues",
        action="opened",
        line="https://github.com/SimonBarnett/bobiverse/issues/3991",
        title="FR: airc-network-installer.exe",
        body="Goal: ship installer.",
        labels=("hold",),
    )
    changed = gitclaim._append_unaccepted(doc, claim, url=claim.line)
    assert changed == "skipped"
    assert doc["unaccepted"] == []


def test_append_unaccepted_skips_fr_when_hold_body(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    doc = gitclaim._empty_queue()
    claim = gitclaim.GitClaim(
        repo="SimonBarnett/bobiverse",
        task="FR",
        id="3991",
        event="issues",
        action="opened",
        line="https://github.com/SimonBarnett/bobiverse/issues/3991",
        title="FR: airc-network-installer.exe",
        body=HOLD_BODY,
        labels=(),
    )
    changed = gitclaim._append_unaccepted(doc, claim, url=claim.line)
    assert changed == "skipped"
    assert doc["unaccepted"] == []


def test_append_unaccepted_drops_existing_when_hold_appears(tmp_path):
    """Webhook edited / resync: hold on an already-queued FR must remove it."""
    doc = gitclaim._empty_queue()
    doc["unaccepted"].append(
        {
            "repo": "SimonBarnett/bobiverse",
            "task": "FR",
            "id": "#3991",
            "url": "https://github.com/SimonBarnett/bobiverse/issues/3991",
            "title": "FR: airc-network-installer.exe",
            "body": "Goal",
            "labels": [],
        }
    )
    claim = gitclaim.GitClaim(
        repo="SimonBarnett/bobiverse",
        task="FR",
        id="3991",
        event="issues",
        action="edited",
        line="https://github.com/SimonBarnett/bobiverse/issues/3991",
        title="FR: airc-network-installer.exe",
        body=HOLD_BODY,
        labels=("hold",),
    )
    changed = gitclaim._append_unaccepted(doc, claim, url=claim.line)
    assert changed == "skipped"
    assert doc["unaccepted"] == []


def test_row_fr_hold_reason_on_queue_row():
    row = {
        "task": "FR",
        "repo": "SimonBarnett/bobiverse",
        "id": "3991",
        "title": "FR: installer",
        "labels": ["hold"],
    }
    assert gitclaim.row_fr_hold_reason(row)
    row_mrb = {"task": "MRB", "labels": ["hold"], "title": "x"}
    assert gitclaim.row_fr_hold_reason(row_mrb) is None
