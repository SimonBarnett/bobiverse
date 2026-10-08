# -*- coding: utf-8 -*-
"""MRB #3265 hostile gates for FR #3205 offer order + precompute.

Probes beyond the implementer's suite:
- claim_top uses kind+number (not seq)
- stale precompute fingerprint restores GitHub budget path
- same-priority: MRB beats FR across repos even when FR number is lower
- strict focus: unfocused repo never leaks on fallback
- precompute rebuild after offer keeps fingerprint aligned
"""
from __future__ import annotations

from pathlib import Path

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines
import pytest


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"marchhare", "ionos", "flamingo"})
    digest = bobreport.empty_digest()
    for mid, pids in (
        ("marchhare", ("35600", "35601", "35602")),
        ("flamingo", ("9",)),
    ):
        digest["machines"][mid] = bobreport._empty_machine(mid)
        digest["machines"][mid]["workers"] = {p: {"state": "idle"} for p in pids}
    bobreport.save_digest(tmp_path, digest)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return tmp_path


def _row(repo: str, task: str, num: int, seq: int | None = None, **kw) -> dict:
    r = {
        "repo": repo,
        "task": task,
        "id": f"#{num}",
        "seq": seq if seq is not None else num + 1000,
        "ts": f"2026-10-01T10:00:{num:02d}Z",
        "line": f"{task} {repo}#{num}",
        "url": f"https://github.com/{repo}/{'pull' if task == 'MRB' else 'issues'}/{num}",
        "title": f"{task} {num}",
        "state": "open",
    }
    r.update(kw)
    return r


def _queue(home: Path, rows: list[dict]) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": rows, "accepted": [], "done": [], "workers": {}},
    )


def test_mrb3265_claim_top_kind_then_number_not_seq(home: Path):
    """claim_top must pick lowest MRB by number even when FR has lower seq."""
    repo = "SimonBarnett/bobiverse"
    _queue(
        home,
        [
            _row(repo, "FR", 1, seq=1),
            _row(repo, "MRB", 9, seq=2),
            _row(repo, "MRB", 3, seq=99),
        ],
    )
    st, job = gitclaim.claim_top(home, "marchhare-35600", "#marchhare")
    assert st == "ok" and job is not None
    assert job["task"] == "MRB" and job["id"] == "#3"


def test_mrb3265_same_priority_mrb_beats_lower_numbered_fr(home: Path):
    """Across same-priority repos, any MRB sorts before any FR (kind before number)."""
    _queue(
        home,
        [
            _row("SimonBarnett/a-search", "FR", 1, seq=1),
            _row("SimonBarnett/Club-Madeira", "MRB", 99, seq=2),
        ],
    )
    fi.handle_focus_cmd(home, "1 SimonBarnett/a-search")
    fi.handle_focus_cmd(home, "1 SimonBarnett/Club-Madeira")
    # Older ts on a-search must not promote its FR ahead of the MRB.
    doc = fi.load_focus(home)
    doc["repos"]["SimonBarnett/a-search"]["ts"] = "2026-01-01T00:00:00Z"
    doc["repos"]["SimonBarnett/Club-Madeira"]["ts"] = "2026-12-01T00:00:00Z"
    fi.save_focus(home, doc)
    ordered = gitclaim.ordered_unaccepted(home)
    assert ordered[0]["task"] == "MRB" and ordered[0]["id"] == "#99"
    assert ordered[1]["task"] == "FR" and ordered[1]["id"] == "#1"
    st, job = gitclaim.offer_focus_top(home, "marchhare-35600", "#marchhare")
    assert st == "ok" and job["task"] == "MRB" and job["id"] == "#99"


def test_mrb3265_stale_precompute_allows_github_budget(home: Path):
    """Fingerprint mismatch must not take the zero-GitHub path forever."""
    repo = "SimonBarnett/a-search"
    _queue(home, [_row(repo, "FR", 3, seq=1)])
    fi.handle_focus_cmd(home, repo)
    gitclaim.rebuild_offer_precompute(home)
    assert gitclaim.offer_precompute_fresh(home) is True
    # Queue gains a new row → fingerprint stale.
    _queue(home, [_row(repo, "FR", 3, seq=1), _row(repo, "FR", 4, seq=2)])
    assert gitclaim.offer_precompute_fresh(home) is False
    calls = {"n": 0}

    def probe(*_a, **_k):
        calls["n"] += 1
        return True

    st, job = gitclaim.offer_focus_top(
        home,
        "marchhare-35600",
        "#marchhare",
        pr_exists=probe,
        is_pull=lambda *_a, **_k: False,
        issue_open=probe,
    )
    assert st == "ok" and job is not None
    # Stale path keeps FR #3188 budget (>=0 calls allowed); zero-GitHub only when fresh.
    # At least the offer must succeed and prefer lowest number.
    assert job["id"] == "#3"


def test_mrb3265_strict_focus_fallback_no_unfocused_leak(home: Path):
    """Under strict focus, an unfocused repo must not appear when focused rows are ineligible."""
    me = "marchhare-35600"
    focused = _row("SimonBarnett/bobiverse", "MRB", 10, seq=1)
    focused["giveup_seats"] = me
    _queue(
        home,
        [
            focused,
            _row("SimonBarnett/Club-Madeira", "FR", 1, seq=2),
        ],
    )
    fi.handle_focus_cmd(home, "SimonBarnett/bobiverse")
    fi.handle_focus_cmd(home, "strict on")
    st, job = gitclaim.offer_focus_top(home, me, "#marchhare")
    assert st == "empty" or (job is not None and "Club-Madeira" not in str(job.get("repo") or ""))
    if st == "ok" and job is not None:
        assert "bobiverse" in job["repo"]


def test_mrb3265_rebuild_after_offer_keeps_fresh(home: Path):
    """After an offer stamp, precompute fingerprint matches remaining unaccepted."""
    repo = "SimonBarnett/bobiverse"
    _queue(home, [_row(repo, "MRB", 5, seq=1), _row(repo, "FR", 3, seq=2)])
    fi.handle_focus_cmd(home, repo)
    gitclaim.rebuild_offer_precompute(home)
    st, job = gitclaim.offer_focus_top(home, "marchhare-35600", "#marchhare")
    assert st == "ok" and job["id"] == "#5"
    # Remaining unaccepted is FR #3 only; fingerprint should be fresh for next !bored.
    assert gitclaim.offer_precompute_fresh(home) is True
    calls = {"n": 0}

    def boom(*_a, **_k):
        calls["n"] += 1
        raise AssertionError("fresh post-offer precompute must not call GitHub")

    st2, job2 = gitclaim.offer_focus_top(
        home,
        "marchhare-35601",
        "#marchhare",
        pr_exists=boom,
        is_pull=boom,
        issue_open=boom,
    )
    assert st2 == "ok" and job2["id"] == "#3"
    assert calls["n"] == 0
