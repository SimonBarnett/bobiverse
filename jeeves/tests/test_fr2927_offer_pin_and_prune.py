"""FR #2927: #2900 dead-pin / heal must not break one-offer-per-job or fake-MRB prune."""
from __future__ import annotations

import time

import gitclaim


def test_fr2927_empty_live_keeps_one_offer_per_job(tmp_path, monkeypatch):
    """No digest workers → sticky offered_to until timeout (not immediate clear)."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rows = [
        {
            "repo": "o/a",
            "task": "FR",
            "id": "#1",
            "seq": 1,
            "url": "https://github.com/o/a/issues/1",
        },
        {
            "repo": "o/b",
            "task": "FR",
            "id": "#2",
            "seq": 2,
            "url": "https://github.com/o/b/issues/2",
        },
    ]
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path), {"v": 1, "unaccepted": rows, "accepted": [], "done": []}
    )
    t0 = time.time()
    _s1, j1 = gitclaim.offer_focus_top(tmp_path, "ionos-1", "#ionos", now=t0)
    _s2, j2 = gitclaim.offer_focus_top(tmp_path, "ionos-2", "#ionos", now=t0 + 5)
    assert (j1["id"], j2["id"]) == ("#1", "#2")


def test_fr2927_heal_skips_bare_fake_mrb():
    row = {
        "repo": "SimonBarnett/bobiverse",
        "task": "MRB",
        "id": "#227",
        "line": "fake",
    }
    assert gitclaim._mrb_row_has_pull_provenance(row) is False
    assert gitclaim._heal_mrb_pull_url(row) is False
    assert not row.get("url")


def test_fr2927_heal_lesson_missing_url():
    row = {
        "repo": "SimonBarnett/bobiverse",
        "task": "MRB",
        "id": "#2896",
        "title": "lesson(bobiverse-bob-worker): x",
        "labels": ["harvest-lesson"],
        "event": "pull_request",
    }
    assert gitclaim._heal_mrb_pull_url(row) is True
    assert "/pull/2896" in str(row.get("url") or "")
