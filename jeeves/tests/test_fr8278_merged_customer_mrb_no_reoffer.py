# -*- coding: utf-8 -*-
"""FR #8278 / FR #9885: PASS on open clean mergeable MRBs keep queue + mrb_done until merge.

Customer repos with allow_auto_merge=false (e.g. toray#28) stay open after DONE PASS.
Rows with mergeable_state clean stay in unaccepted for other seats (FR #9885); the
seat that PASSed is blocked by FR #4661. mrb_done stamp still survives resync ci-wait.
"""
from __future__ import annotations

from pathlib import Path

import gitclaim

TORAY = "SimonBarnett/toray"


def _mrb(num=28, repo=TORAY, **extra):
    row = {
        "repo": repo,
        "task": "MRB",
        "id": f"#{num}",
        "seq": 1,
        "ts": "t",
        "line": f"MRB {repo}#{num}",
        "url": f"https://github.com/{repo}/pull/{num}",
        "mergeable": True,
        "mergeable_state": "clean",
    }
    row.update(extra)
    return row


def test_fr8278_pass_blocks_reoffer_while_pr_still_open(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim.stamp_mrb_done(tmp_path, TORAY, "#28")
    doc = {
        "v": 1,
        "unaccepted": [_mrb(28)],
        "accepted": [],
        "done": [_mrb(28, result="PASS", nick="redqueen-1")],
    }

    def pr_open(repo: str, num: str) -> bool:
        return repo == TORAY and str(num).lstrip("#") == "28"

    assert gitclaim._mrb_review_finished(doc, tmp_path, TORAY, "#28") is True
    assert (
        gitclaim.mrb_already_done(doc, doc["unaccepted"][0], home=tmp_path, pr_exists=pr_open)
        is False
    )
    n = gitclaim._purge_dead_mrb_unaccepted(doc, pr_exists=pr_open, home=tmp_path)
    assert n == 0
    assert len(doc["unaccepted"]) == 1
    # Stamp must survive the open-PR clear path.
    assert gitclaim.mrb_ledger_done_hold(tmp_path, TORAY, "#28") is True


def test_fr8278_premature_done_without_pass_still_yields_to_open(tmp_path, monkeypatch):
    """FR #1585: ledger-only stamp (no PASS) still clears when GitHub says open."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim.stamp_mrb_done(tmp_path, TORAY, "#28")
    doc = {
        "v": 1,
        "unaccepted": [_mrb(28)],
        "accepted": [],
        "done": [],  # no verdict
    }

    def pr_open(repo: str, num: str) -> bool:
        return repo == TORAY and str(num).lstrip("#") == "28"

    assert gitclaim._mrb_review_finished(doc, tmp_path, TORAY, "#28") is False
    assert (
        gitclaim.mrb_already_done(doc, doc["unaccepted"][0], home=tmp_path, pr_exists=pr_open)
        is False
    )
    n = gitclaim._purge_dead_mrb_unaccepted(doc, pr_exists=pr_open, home=tmp_path)
    assert n == 0
    assert len(doc["unaccepted"]) == 1
    assert gitclaim.mrb_ledger_done_hold(tmp_path, TORAY, "#28") is False


def test_fr8278_bored_path_skips_after_pass_even_without_pr_exists(tmp_path, monkeypatch):
    """!bored uses pr_exists=None; PASS in done[] must still block."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    doc = {
        "v": 1,
        "unaccepted": [_mrb(28)],
        "accepted": [],
        "done": [_mrb(28, result="PASS", done_by="redqueen-1")],
    }
    assert (
        gitclaim.mrb_already_done(doc, doc["unaccepted"][0], home=tmp_path, pr_exists=None)
        is False
    )
    n = gitclaim._purge_dead_mrb_unaccepted(doc, pr_exists=None, home=tmp_path)
    assert n == 0
    assert len(doc["unaccepted"]) == 1


def test_fr8278_resync_keeps_mrb_done_when_pass_recorded(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim.stamp_mrb_done(tmp_path, TORAY, "#28")
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [],
            "done": [_mrb(28, result="PASS", nick="redqueen-1")],
        },
    )

    def fetch(url: str):
        if "/pulls" in url and "state=closed" not in url:
            return [
                {
                    "number": 28,
                    "title": "harvest: park",
                    "body": "Closes SimonBarnett/toray#27",
                    "html_url": f"https://github.com/{TORAY}/pull/28",
                    "state": "open",
                    "user": {"login": "u"},
                    "head": {"sha": "6f80f22e478c3e9c6b67759d3bea1438ce1457b2", "ref": "fix-28"},
                    "draft": False,
                }
            ]
        if "/issues" in url:
            return []
        return []

    res = gitclaim.resync_from_github(tmp_path, [TORAY], fetch_json=fetch)
    assert res.get("ok") is True
    # PASS on record → do not clear the DONE hold (ci-wait).
    assert gitclaim.mrb_ledger_done_hold(tmp_path, TORAY, "#28") is True
