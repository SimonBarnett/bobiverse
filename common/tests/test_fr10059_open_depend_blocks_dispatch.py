"""FR #10059: OPEN Depends-on blocks offer and !assign, including an unheld digest."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

gitclaim = importlib.import_module("gitclaim")

REPO = "SimonBarnett/bobiverse"


def _row(num, body, task="FR"):
    return {
        "repo": REPO,
        "task": task,
        "id": str(num),
        "title": "child",
        "body": body,
        "state": "open",
        "labels": ["feature-request"],
    }


def _digest(num):
    return {
        "repo": REPO,
        "task": "FR",
        "id": str(num),
        "title": "Digest: parent",
        "body": "Kind: fr-digest\n",
        "state": "open",
        "labels": ["feature-request", "fr-digest"],
    }


def test_fr10059_unheld_open_digest_blocks_fr_fix_and_mrb():
    parent = _digest(9798)
    doc = {"unaccepted": [parent], "accepted": [], "done": []}
    keys = gitclaim.open_fr_issue_keys(doc)
    for task in ("FR", "FIX", "MRB"):
        child = _row(9810, "Depends-on: #9798\n", task=task)
        why = gitclaim.depends_gate_reason(child, doc, open_keys=keys)
        assert why == gitclaim.DEPENDS_OPEN_REASON, (task, why)


def test_fr10059_unknown_without_checker_fails_closed():
    child = _row(9810, "Depends-on: #9798\n")
    doc = {"unaccepted": [child], "accepted": [], "done": []}
    why = gitclaim.depends_gate_reason(child, doc, open_keys=set(), issue_open=None)
    assert why == gitclaim.DEPENDS_UNRESOLVED_REASON


def test_fr10059_closed_parent_clears():
    child = _row(9810, "Depends-on: #9798\n")
    doc = {"unaccepted": [child], "accepted": [], "done": []}
    why = gitclaim.depends_gate_reason(
        child,
        doc,
        open_keys=set(),
        issue_open=lambda repo, num: False,
    )
    assert why is None


def test_fr10059_assign_reason_names_the_open_issue():
    child = _row(9810, "Depends-on: #9798\n", task="FIX")
    assert gitclaim._depends_open_assign_reason(child) == "depends-on open #9798"
