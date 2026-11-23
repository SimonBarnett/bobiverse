"""FR #9220: Depends-on open-FR index is repo-scoped (no cross-repo #N collision)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

gitclaim = importlib.import_module("gitclaim")


def test_fr9220_relative_hash_not_blocked_by_other_repo_same_number():
    """a/home#10 Depends-on #9 must not see b/other#9 as open."""
    doc = gitclaim._empty_queue()
    doc["unaccepted"].extend(
        [
            {
                "repo": "b/other",
                "task": "FR",
                "id": "#9",
                "title": "unrelated other#9",
                "body": "dispatched",
            },
            {
                "repo": "a/home",
                "task": "FR",
                "id": "#10",
                "title": "needs #9 in same repo",
                "body": "**Depends-on:** #9\n",
            },
        ]
    )
    why = gitclaim.row_fr_depends_blocked_reason(doc["unaccepted"][1], doc)
    assert why is None, why


def test_fr9220_relative_hash_blocked_when_same_repo_open():
    doc = gitclaim._empty_queue()
    doc["unaccepted"].extend(
        [
            {
                "repo": "a/home",
                "task": "FR",
                "id": "#9",
                "title": "dep",
                "body": "dispatched",
            },
            {
                "repo": "a/home",
                "task": "FR",
                "id": "#10",
                "title": "needs #9",
                "body": "**Depends-on:** #9\n",
            },
        ]
    )
    why = gitclaim.row_fr_depends_blocked_reason(doc["unaccepted"][1], doc)
    assert why
    assert "#9" in why


def test_fr9220_qualified_ref_uses_named_repo_not_home_number():
    """Depends-on a/home#9 blocks only when a/home#9 is open, not b/other#9."""
    doc = gitclaim._empty_queue()
    doc["unaccepted"].extend(
        [
            {
                "repo": "b/other",
                "task": "FR",
                "id": "#9",
                "title": "other",
                "body": "dispatched",
            },
            {
                "repo": "x/caller",
                "task": "FR",
                "id": "#1",
                "title": "caller",
                "body": "**Depends-on:** a/home#9\n",
            },
        ]
    )
    why = gitclaim.row_fr_depends_blocked_reason(doc["unaccepted"][1], doc)
    assert why is None, why

    doc["unaccepted"].append(
        {
            "repo": "a/home",
            "task": "FR",
            "id": "#9",
            "title": "real dep",
            "body": "dispatched",
        }
    )
    why2 = gitclaim.row_fr_depends_blocked_reason(doc["unaccepted"][1], doc)
    assert why2
    assert "a/home" in why2.lower() or "#9" in why2


def test_fr9220_parse_keeps_qualified_token():
    toks = gitclaim.parse_depends_on_tokens("Depends-on: a/home#9, #3\n")
    assert "a/home#9" in toks or any(t.lower() == "a/home#9" for t in toks)
    assert "#3" in toks
    # bare #9 must not be synthesized from the qualified ref alone
    # (qualified + separate #3 only)
    assert toks.count("#9") == 0