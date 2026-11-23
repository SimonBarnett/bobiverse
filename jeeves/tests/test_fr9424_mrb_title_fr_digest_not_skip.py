# -*- coding: utf-8 -*-
"""FR #9424: MRB titles mentioning fr-digest must not skip as label_text:fr-digest.

Incident: !assign MRB #9420 / skills-visionary#221 refused label_text:fr-digest
while PR labels were empty — title named the feature.
"""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import registered_machines
import pytest

REPO = "SimonBarnett/bobiverse"
NICK = "redqueen-13496"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"redqueen", "flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["redqueen"] = bobreport._empty_machine("redqueen")
    digest["machines"]["redqueen"]["worker_list"] = [
        {
            "nick": NICK,
            "state": "idle",
            "kind": "grok",
            "start_model": "grok-4",
            "configured_model": "grok-4",
            "updated": "2026-11-23T18:58:00Z",
        }
    ]
    bobreport.save_digest(tmp_path, digest)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return tmp_path


def test_fr_digest_not_in_skip_fr_labels_in_text():
    assert "fr-digest" in gitclaim.SKIP_FR_LABELS
    assert "fr-digest" not in gitclaim.SKIP_FR_LABELS_IN_TEXT


def test_issue_skip_empty_labels_title_mentions_fr_digest_ok():
    why = gitclaim.issue_skip_fr_reason(
        title="FR #9418: BOB-G1 live digest when fr-digest absent from queue",
        body="Implement the gate.\n",
        labels=(),
    )
    assert why is None


def test_mrb_row_title_fr_digest_not_skipped():
    row = {
        "repo": REPO,
        "task": "MRB",
        "id": "#9420",
        "title": "FR #9418: BOB-G1 live digest when fr-digest absent from queue",
        "body": "",
        "labels": [],
        "url": f"https://github.com/{REPO}/pull/9420",
        "event": "pull_request",
        "line": f"MRB {REPO}#9420",
    }
    assert gitclaim.row_skip_fr_reason(row) is None


def test_skills_visionary_mrb_title_not_skipped():
    row = {
        "repo": "SimonBarnett/skills-visionary",
        "task": "MRB",
        "id": "#221",
        "title": "FR #220: VIS-G5 no double-park child hold on fr-digest batches",
        "body": "",
        "labels": [],
        "url": "https://github.com/SimonBarnett/skills-visionary/pull/221",
        "event": "pull_request",
    }
    assert gitclaim.row_skip_fr_reason(row) is None


def test_real_fr_digest_label_still_skips():
    why = gitclaim.issue_skip_fr_reason(
        title="Digest: BOB-TRAY-UI",
        body="go-gate\n",
        labels=("feature-request", "fr-digest"),
    )
    assert why == "label:fr-digest"


def test_kind_fr_digest_body_still_skips():
    why = gitclaim.issue_skip_fr_reason(
        title="Digest: go-gate",
        body="Kind: fr-digest\n\nNot an implementation ticket.\n",
        labels=("feature-request",),
    )
    assert why == "fr_digest_kind"


def test_assign_mrb_with_fr_digest_in_title(home: Path):
    """!assign must not refuse label_text:fr-digest for an ordinary MRB PR tip."""
    row = {
        "repo": REPO,
        "task": "MRB",
        "id": "#9420",
        "seq": 1,
        "ts": "2026-11-23T18:58:00Z",
        "title": "FR #9418: BOB-G1 live digest when fr-digest absent from queue",
        "body": "",
        "labels": [],
        "url": f"https://github.com/{REPO}/pull/9420",
        "line": f"https://github.com/{REPO}/pull/9420",
        "event": "pull_request",
        "state": "open",
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [row],
            "accepted": [],
            "done": [],
            "workers": {NICK: {"last_seen": 9e12}},
        },
    )
    st, why = gitclaim.assign_row(
        home,
        NICK,
        REPO,
        "MRB",
        "9420",
        is_pull=lambda *_a, **_k: True,
        pr_exists=lambda *_a, **_k: True,
        issue_open=lambda *_a, **_k: True,
    )
    assert st != "refused" or "label_text:fr-digest" not in str(why)
    if st == "refused":
        # May refuse for other legitimate reasons (self-MRB, model, …) but never this.
        assert "fr-digest" not in str(why)
    else:
        assert st == "ok"
