"""FR #6203: self-review-deadlock still reports when no eligible reviewer.

FR #6112 dropped harvest tips from the waiting set and silenced author-only
idle when cloud eligibility cannot be checked (no home). With home present,
mrb_has_eligible_reviewer must still run so Copilot backoff + author-only
idle files a genuine deadlock.
"""
from __future__ import annotations

from pathlib import Path

import gitclaim
import stall_detectors as sd


def _product_row(author: str, rid: str = "#1") -> dict:
    num = str(rid).lstrip("#")
    return {
        "task": "MRB",
        "repo": "SimonBarnett/bobiverse",
        "id": rid,
        "url": "https://github.com/SimonBarnett/bobiverse/pull/" + num,
        "title": "FR %s product" % rid,
        "author_seat": author,
    }


def test_fr6203_eligible_non_author_idle_is_silent():
    found = sd.detect_self_review_deadlock(
        {
            "live": {"flamingo-1", "marchhare-1"},
            "idle": {"flamingo-1", "marchhare-1"},
            "unaccepted": [_product_row("flamingo-1")],
            "accepted": [],
            "ledger": {},
        }
    )
    assert found == []


def test_fr6203_author_only_without_home_still_silent_fr6112():
    found = sd.detect_self_review_deadlock(
        {
            "live": {"flamingo-1"},
            "idle": {"flamingo-1"},
            "unaccepted": [_product_row("flamingo-1")],
            "accepted": [],
            "ledger": {},
        }
    )
    assert found == []


def test_fr6203_harvest_lesson_mixed_still_silent_fr6112():
    found = sd.detect_self_review_deadlock(
        {
            "live": {"flamingo-1"},
            "idle": {"flamingo-1"},
            "unaccepted": [
                _product_row("flamingo-1", "#6110"),
                {
                    "task": "MRB",
                    "repo": "SimonBarnett/bobiverse",
                    "id": "#6111",
                    "url": "https://github.com/SimonBarnett/bobiverse/pull/6111",
                    "title": "lesson(bobiverse-fleet-ops): tip",
                    "labels": ["harvest-lesson"],
                    "author_seat": "flamingo-1",
                    "harvest_lesson": True,
                },
            ],
            "accepted": [],
            "ledger": {},
        }
    )
    assert found == []


def test_fr6203_home_present_author_only_no_eligible_reports(tmp_path, monkeypatch):
    """With home, author-only idle and no eligible reviewer must file."""
    import copilot_dispatch as cd

    monkeypatch.setattr(cd, "mrb_reviewer_available", lambda *a, **k: False)
    monkeypatch.setattr(gitclaim, "mrb_has_eligible_reviewer", lambda *a, **k: False)
    found = sd.detect_self_review_deadlock(
        {
            "home": tmp_path,
            "live": {"flamingo-1"},
            "idle": {"flamingo-1"},
            "unaccepted": [_product_row("flamingo-1")],
            "accepted": [],
            "ledger": {},
            "now": 1_700_000_000.0,
        }
    )
    assert len(found) == 1
    assert found[0]["id"] == sd.SELF_REVIEW_ID


def test_fr6203_busy_eligible_non_author_suppresses_deadlock(tmp_path, monkeypatch):
    """MRB #6205: pass live to mrb_has_eligible_reviewer; busy reviewer is enough."""
    import copilot_dispatch as cd
    import focus_ignore
    import registered_machines

    monkeypatch.setenv('BOB_DIGEST_HOME', str(tmp_path))
    registered_machines.save_registered(tmp_path, {'flamingo', 'marchhare'})
    monkeypatch.setattr(cd, 'is_high_priority', lambda *_: True)
    focus_ignore.handle_focus_cmd(tmp_path, 'high SimonBarnett/bobiverse')
    cd.set_allowance(tmp_path, remaining=100)
    author = 'flamingo-72904'
    now = 1_800_000_000.0
    rows = [
        {
            'repo': 'SimonBarnett/bobiverse', 'task': 'MRB', 'id': '#%d' % n,
            'title': 'Review change', 'author_seat': author,
            'url': 'https://github.com/SimonBarnett/bobiverse/pull/%d' % n,
            'ts': cd._utc_iso(now), 'seq': n,
        }
        for n in range(1, 5)
    ]
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {'v': 1, 'unaccepted': rows, 'accepted': [], 'done': []},
    )
    for n, row in enumerate(rows[:3]):
        start = now + n * 60
        assert cd.dispatch_row(
            tmp_path, row, now=start, post=lambda *_: {'id': 'task-%d' % n}
        )['status'] == 'dispatched'
        job = cd._load_jobs(tmp_path)['jobs'][-1]
        assert cd.handle_timeout_or_fail(
            tmp_path, job, now=start + 40, reason='failed'
        )['status'] == 'giveup'
    waiting = gitclaim.load_unaccepted(tmp_path)
    found = sd.detect_self_review_deadlock(
        {
            'home': tmp_path,
            'now': now + 180,
            'live': {author, 'marchhare-2'},
            'idle': {author},
            'unaccepted': waiting,
            'accepted': [],
            'ledger': {},
        }
    )
    assert found == []


def test_fr6203_harvest_mixed_home_present_reports_product_only(tmp_path, monkeypatch):
    """With home, harvest-lesson rows stay dropped from waiting (FR #6112)."""
    import copilot_dispatch as cd

    monkeypatch.setattr(cd, 'mrb_reviewer_available', lambda *a, **k: False)
    monkeypatch.setattr(gitclaim, 'mrb_has_eligible_reviewer', lambda *a, **k: False)
    found = sd.detect_self_review_deadlock(
        {
            'home': tmp_path,
            'live': {'flamingo-1'},
            'idle': {'flamingo-1'},
            'unaccepted': [
                _product_row('flamingo-1', '#6110'),
                {
                    'task': 'MRB',
                    'repo': 'SimonBarnett/bobiverse',
                    'id': '#6111',
                    'url': 'https://github.com/SimonBarnett/bobiverse/pull/6111',
                    'title': 'lesson(bobiverse-fleet-ops): tip',
                    'labels': ['harvest-lesson'],
                    'author_seat': 'flamingo-1',
                    'harvest_lesson': True,
                },
            ],
            'accepted': [],
            'ledger': {},
            'now': 1_700_000_000.0,
        }
    )
    assert len(found) == 1
    assert found[0]['id'] == sd.SELF_REVIEW_ID
    assert found[0]['key'] == 'SimonBarnett/bobiverse#6110'
    assert found[0]['evidence']['waiting'] == ['SimonBarnett/bobiverse#6110']
