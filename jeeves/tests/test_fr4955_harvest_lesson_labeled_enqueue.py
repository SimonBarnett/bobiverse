"""FR #4955: harvest-lesson pull_request labeled backfills MRB when opened was missed."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim

REPO = "SimonBarnett/a-search"


def _pr_payload(action: str, num: int, *, labels=None, title: str | None = None, draft: bool = False):
    return {
        "action": action,
        "repository": {"full_name": REPO},
        "label": {"name": (labels or ["x"])[-1] if action in ("labeled", "unlabeled") else "x"},
        "pull_request": {
            "number": num,
            "title": title or f"pr {num}",
            "body": (
                "Lessons:\n- fixture selftest vendor secrets\n\n"
                "---\n_source machine=`flamingo` agent=`Invoke-BobiverseHarvest` "
                "book=`harvest-agent-skills` ver=`-` seat=`flamingo-15516`_\n"
            ),
            "merged": False,
            "draft": draft,
            "state": "open",
            "html_url": f"https://github.com/{REPO}/pull/{num}",
            "labels": [{"name": n} for n in (labels or [])],
        },
    }


def test_opened_lesson_title_without_harvest_label_enqueues(tmp_path: Path):
    """Title lesson(book): is enough; do not wait for harvest-lesson."""
    out = bobreport.apply_git_webhook(
        tmp_path,
        "pull_request",
        _pr_payload(
            "opened",
            4866,
            labels=["via-intake"],
            title="lesson(harvest-agent-skills): Fixture-only /selftest probes",
        ),
    )
    assert out.ok, out.err
    rows = [r for r in gitclaim.load_unaccepted(tmp_path) if r.get("id") == "#4866"]
    assert len(rows) == 1
    assert rows[0]["task"] == "MRB"
    assert rows[0].get("url") == f"https://github.com/{REPO}/pull/4866"


def test_labeled_harvest_lesson_backfills_missing_mrb(tmp_path: Path):
    """If opened missed the queue, labeled harvest-lesson must invent the MRB row."""
    out = bobreport.apply_git_webhook(
        tmp_path,
        "pull_request",
        _pr_payload(
            "labeled",
            4876,
            labels=["via-intake", "harvest-lesson"],
            title="lesson(harvest-agent-skills): Fixture-only /selftest probes must not require vendor secrets",
        ),
    )
    assert out.ok, out.err
    rows = [r for r in gitclaim.load_unaccepted(tmp_path) if r.get("id") == "#4876"]
    assert len(rows) == 1
    assert rows[0]["task"] == "MRB"
    assert "harvest-lesson" in [str(x).lower() for x in (rows[0].get("labels") or [])]
    assert rows[0].get("url") == f"https://github.com/{REPO}/pull/4876"


def test_labeled_plain_product_pr_still_does_not_invent_mrb(tmp_path: Path):
    """Stray harvest-lesson on a product title must not invent an MRB row."""
    out = bobreport.apply_git_webhook(
        tmp_path,
        "pull_request",
        _pr_payload("labeled", 99, labels=["harvest-lesson"], title="fix(selftest): skip MSSQL"),
    )
    assert out.ok, out.err
    ids = {(r["task"], r["id"]) for r in gitclaim.load_unaccepted(tmp_path)}
    assert ("MRB", "#99") not in ids


def test_labeled_draft_lesson_does_not_enqueue(tmp_path: Path):
    out = bobreport.apply_git_webhook(
        tmp_path,
        "pull_request",
        _pr_payload(
            "labeled",
            10,
            labels=["harvest-lesson"],
            title="lesson(harvest): draft tip",
            draft=True,
        ),
    )
    assert out.ok, out.err
    ids = {(r["task"], r["id"]) for r in gitclaim.load_unaccepted(tmp_path)}
    assert ("MRB", "#10") not in ids
