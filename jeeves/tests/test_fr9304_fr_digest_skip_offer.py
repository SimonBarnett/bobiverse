"""FR #9304: label:fr-digest / Kind: fr-digest epics must not offer as implement FRs.

Umbrella digests are go-gate release switches (job-irc ACK then GIVEUP). Chair
offered #9147 as implement FR; exclude them like umbrella / parent-fr.
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

DIGEST_BODY = (
    "Kind: fr-digest\n\n"
    "**Theme:** Depends-on go-gate\n\n"
    "Not an implementation ticket.\n"
)


def test_fr9304_fr_digest_in_skip_fr_labels():
    assert "fr-digest" in gitclaim.SKIP_FR_LABELS


def test_fr9304_issue_skip_fr_reason_label():
    why = gitclaim.issue_skip_fr_reason(
        title="Digest: Depends-on + FR digest go-gate",
        body=DIGEST_BODY,
        labels=("feature-request", "fr-digest"),
    )
    assert why == "label:fr-digest"


def test_fr9304_issue_skip_fr_reason_kind_body_without_label():
    why = gitclaim.issue_skip_fr_reason(
        title="Digest: Depends-on + FR digest go-gate",
        body=DIGEST_BODY,
        labels=("feature-request",),
    )
    assert why == "fr_digest_kind"


def test_fr9304_kind_prose_does_not_false_positive():
    body = (
        "Acceptance: document Kind: fr-digest epics for operators. "
        "Do not put secrets in the body.\n"
    )
    assert (
        gitclaim.issue_skip_fr_reason(
            title="FR: docs for digest go-gate",
            body=body,
            labels=("feature-request",),
        )
        is None
    )


def test_fr9304_product_fr_still_offerable():
    assert (
        gitclaim.issue_skip_fr_reason(
            title="FR #8837: Digest go-gate in offer path",
            body="Implement BOB-G1 chair gate.\n",
            labels=("feature-request",),
        )
        is None
    )


def test_fr9304_digest_does_not_block_repo_uat():
    assert not gitclaim.issue_blocks_repo_uat(
        title="Digest: Depends-on + FR digest go-gate",
        body=DIGEST_BODY,
        labels=("feature-request", "fr-digest"),
    )


def test_fr9304_append_unaccepted_skips_fr_digest_label():
    doc = gitclaim._empty_queue()
    claim = gitclaim.GitClaim(
        repo="SimonBarnett/bobiverse",
        task="FR",
        id="9147",
        event="issues",
        action="opened",
        line="https://github.com/SimonBarnett/bobiverse/issues/9147",
        title="Digest: Depends-on + FR digest go-gate",
        body=DIGEST_BODY,
        labels=("feature-request", "fr-digest"),
    )
    changed = gitclaim._append_unaccepted(doc, claim, url=claim.line)
    assert changed == "skipped"
    assert doc["unaccepted"] == []


def test_fr9304_append_unaccepted_skips_kind_body():
    doc = gitclaim._empty_queue()
    claim = gitclaim.GitClaim(
        repo="SimonBarnett/bobiverse",
        task="FR",
        id="9147",
        event="issues",
        action="opened",
        line="https://github.com/SimonBarnett/bobiverse/issues/9147",
        title="Digest: Depends-on + FR digest go-gate",
        body=DIGEST_BODY,
        labels=("feature-request",),
    )
    changed = gitclaim._append_unaccepted(doc, claim, url=claim.line)
    assert changed == "skipped"
    assert doc["unaccepted"] == []


def test_fr9304_prune_drops_existing_digest_row():
    """Resync/prune: an already-queued digest must leave unaccepted."""
    doc = gitclaim._empty_queue()
    doc["unaccepted"].append(
        {
            "repo": "SimonBarnett/bobiverse",
            "task": "FR",
            "id": "#9147",
            "url": "https://github.com/SimonBarnett/bobiverse/issues/9147",
            "title": "Digest: Depends-on + FR digest go-gate",
            "body": DIGEST_BODY,
            "labels": ["feature-request", "fr-digest"],
            "line": "FR SimonBarnett/bobiverse#9147",
        }
    )
    why = gitclaim.row_skip_fr_reason(doc["unaccepted"][0])
    assert why == "label:fr-digest"
