# -*- coding: utf-8 -*-
"""MRB #9917 fix: Depends-on: (none) must ignore rest of a single-line body."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import depends_on as d  # noqa: E402
import open_children_gate as ocg  # noqa: E402

REPO = "SimonBarnett/bobiverse"


def test_depends_on_none_ignores_trailing_hash_refs_on_same_line():
    body = (
        "**Depends-on:** (none)  Kind: fr-digest ## Children | FR-E | #9749 | "
        "Dispatch | Twin #9738 closed as superseded by #9749"
    )
    assert d.parse_depends_on(body, repo=REPO) == ()


def test_open_children_gate_digest_none_line_not_child_of_fr():
    """Digest flattened body must not register as Depends-on #FR child."""
    issues = [
        {
            "number": 9744,
            "state": "open",
            "repo": REPO,
            "title": "Digest: batch",
            "labels": ["fr-digest", "digest"],
            "body": (
                "**Depends-on:** (none)  Kind: fr-digest ## Children "
                "| FR-E | #9749 | Dispatch sends Weights Copilot model |"
            ),
            "html_url": f"https://github.com/{REPO}/issues/9744",
        },
        {
            "number": 9749,
            "state": "open",
            "repo": REPO,
            "title": "FR-E",
            "labels": ["feature-request"],
            "body": "Depends-on: #9744\n",
            "html_url": f"https://github.com/{REPO}/issues/9749",
        },
    ]
    code, lines = ocg.gate_open_children(REPO, 9749, issues=issues)
    text = "\n".join(lines)
    assert code == 0, text
    assert "FAIL" not in text