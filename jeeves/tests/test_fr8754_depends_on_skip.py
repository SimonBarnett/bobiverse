"""FR #8754: skip FR offer while Depends-on backlog IDs still have open queue FRs."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

gitclaim = importlib.import_module("gitclaim")

DOCS = ROOT / "bob" / "docs"

BOB40_BODY = (
    "Feature request `BOB-40` (dispatched).\n\n"
    "**Vision pack:** bob/docs/feature-request-agents-jeeves-butler-icon-2026-11-21.md\n"
)


def test_parse_depends_on_from_vision_pack():
    tokens = gitclaim.fr_depends_on_tokens(
        title="BOB-40: Agents > Jeeves: butler icon",
        body=BOB40_BODY,
        docs_root=DOCS,
    )
    assert "BOB-33" in tokens


def test_parse_depends_on_line_in_body():
    tokens = gitclaim.fr_depends_on_tokens(
        title="x",
        body="**Depends-on:** BOB-06, BOB-33\n",
        docs_root=None,
    )
    # BOB-06 normalizes via int to BOB-6
    assert "BOB-6" in tokens
    assert "BOB-33" in tokens


def test_row_blocked_when_depend_open_in_queue():
    doc = gitclaim._empty_queue()
    doc["unaccepted"].extend(
        [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#8688",
                "title": "BOB-33: Agents > Jeeves: start Grok Build",
                "body": "Feature request `BOB-33` (dispatched).",
            },
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#8678",
                "title": "BOB-40: Agents > Jeeves: butler icon",
                "body": BOB40_BODY,
            },
        ]
    )
    why = gitclaim.row_fr_depends_blocked_reason(
        doc["unaccepted"][1], doc, docs_root=DOCS
    )
    assert why
    assert "BOB-33" in why
    assert "8688" in why


def test_row_clear_when_depend_leaves_queue():
    doc = gitclaim._empty_queue()
    doc["unaccepted"].append(
        {
            "repo": "SimonBarnett/bobiverse",
            "task": "FR",
            "id": "#8678",
            "title": "BOB-40: Agents > Jeeves: butler icon",
            "body": BOB40_BODY,
        }
    )
    assert (
        gitclaim.row_fr_depends_blocked_reason(
            doc["unaccepted"][0], doc, docs_root=DOCS
        )
        is None
    )


def test_issue_ref_depend_blocks():
    doc = gitclaim._empty_queue()
    doc["unaccepted"].extend(
        [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#8713",
                "title": "BOB-06: Tray menu tree",
                "body": "dispatched",
            },
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#9999",
                "title": "BOB-99: something",
                "body": "**Depends-on:** #8713\n",
            },
        ]
    )
    why = gitclaim.row_fr_depends_blocked_reason(doc["unaccepted"][1], doc)
    assert why
    assert "#8713" in why
