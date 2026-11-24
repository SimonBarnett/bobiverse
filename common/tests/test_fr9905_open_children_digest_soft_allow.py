# -*- coding: utf-8 -*-
"""FR #9905: CI-G1 soft-allow when FR-A Closes while siblings share an fr-digest Depends-on.

Deadlock class: digest FR-A lands with Closes #FR-A while open children still
Depends-on #FR-A (and the same Digest). Hard-fail blocked closing the parent
that unblocks them.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "common" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import open_children_gate as ocg  # noqa: E402

REPO = "SimonBarnett/bobiverse"


def _issue(
    num: int,
    body: str,
    *,
    state: str = "open",
    repo: str = REPO,
    title: str = "",
    labels: list | None = None,
    **kw,
) -> dict:
    row = {
        "number": num,
        "body": body,
        "state": state,
        "repo": repo,
        "title": title or f"Issue {num}",
        "html_url": f"https://github.com/{repo}/issues/{num}",
        "labels": labels or [],
    }
    row.update(kw)
    return row


def test_fr9905_soft_allow_when_children_share_digest_depends_on():
    """PR Closes FR-A (#9857) while FR-B/C Depend-on digest + FR-A => exit 0."""
    issues = [
        _issue(
            9856,
            "Kind: fr-digest\n",
            title="Digest: Nested Depends-on",
            labels=["fr-digest", "digest", "feature-request"],
        ),
        _issue(9857, "Depends-on: #9856\n", title="FR-A walk"),
        _issue(9858, "Depends-on: #9856 #9857\n", title="FR-B child"),
        _issue(9860, "Depends-on: #9856\nDepends-on: #9857\n", title="FR-C child"),
    ]
    code, lines = ocg.gate_open_children(REPO, 9857, issues=issues)
    text = "\n".join(lines)
    assert code == 0, text
    assert "soft-allow" in text.lower() or "digest-chain" in text.lower()
    assert "9858" in text or "ok" in text.lower()


def test_fr9905_still_fail_without_shared_digest():
    """Open child Depends-on #P only (no shared digest) => still FAIL."""
    issues = [
        _issue(10, "body\n", title="lone parent"),
        _issue(11, "Depends-on: #10\n", title="orphan child"),
    ]
    code, lines = ocg.gate_open_children(REPO, 10, issues=issues)
    assert code == 1
    assert "FAIL" in "\n".join(lines)


def test_fr9905_still_fail_when_closing_digest_itself():
    """Closing an fr-digest parent with open Depends-on children stays hard-fail."""
    issues = [
        _issue(
            100,
            "Kind: fr-digest\n",
            title="Digest: batch",
            labels=["fr-digest", "digest"],
        ),
        _issue(101, "Depends-on: #100\n", title="child of digest"),
    ]
    code, lines = ocg.gate_open_children(REPO, 100, issues=issues)
    assert code == 1
    assert "FAIL" in "\n".join(lines)


def test_fr9905_cli_pr_closes_fr_a_soft_allow(tmp_path: Path):
    issues_path = tmp_path / "issues.json"
    issues_path.write_text(
        json.dumps(
            [
                _issue(
                    9856,
                    "Kind: fr-digest\n",
                    labels=["fr-digest", "digest"],
                    title="Digest",
                ),
                _issue(9857, "Depends-on: #9856\n", title="FR-A"),
                _issue(9858, "Depends-on: #9856 #9857\n", title="FR-B"),
            ]
        ),
        encoding="utf-8",
    )
    pr_path = tmp_path / "pr.json"
    pr_path.write_text(
        json.dumps(
            {
                "number": 9874,
                "body": "Closes SimonBarnett/bobiverse#9857\n",
                "closingIssuesReferences": [
                    {
                        "number": 9857,
                        "repository": {
                            "name": "bobiverse",
                            "owner": {"login": "SimonBarnett"},
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    rc = ocg.main(
        [
            "--repo",
            REPO,
            "--pr-json",
            str(pr_path),
            "--issues-json",
            str(issues_path),
        ]
    )
    assert rc == 0


def test_fr9905_mixed_child_without_digest_still_fails():
    """One sibling shares the digest; another Depends-on #P only => FAIL."""
    issues = [
        _issue(50, "Kind: fr-digest\n", labels=["fr-digest"], title="Digest"),
        _issue(51, "Depends-on: #50\n", title="FR-A"),
        _issue(52, "Depends-on: #50 #51\n", title="good child"),
        _issue(53, "Depends-on: #51\n", title="bad child no digest"),
    ]
    code, lines = ocg.gate_open_children(REPO, 51, issues=issues)
    assert code == 1
    text = "\n".join(lines)
    assert "FAIL" in text
    assert "#53" in text or "53" in text
