"""FR #8153: no re-offer after deterministic no-clone NACK; repo-level seat block."""
from __future__ import annotations

import time
from datetime import datetime, timezone

import bobreport
import chan_workers
import gitclaim
import registered_machines
import shop_listen

REPO = "SimonBarnett/priority-mcp"
REPO_ALIAS = "SimonBarnett/agentic_fomprep"
TORAY = "SimonBarnett/toray"
SEAT_A = "redqueen-13916"
SEAT_B = "flamingo-20001"


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"redqueen", "flamingo"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    digest["machines"]["redqueen"] = bobreport._empty_machine("redqueen")
    digest["machines"]["redqueen"]["worker_list"] = [
        {"nick": SEAT_A, "state": "idle"},
    ]
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": SEAT_B, "state": "idle"},
    ]
    bobreport.save_digest(tmp_path, digest)
    return tmp_path


def _row(repo: str, task: str, num: int, **kw):
    r = {
        "repo": repo,
        "task": task,
        "id": f"#{num}",
        "seq": num,
        "ts": "2026-11-17T22:40:00Z",
        "line": "x",
        "url": f"https://github.com/{repo}/pull/{num}",
        "title": f"{task} {num}",
        "giveup_count": 0,
    }
    r.update(kw)
    return r


def test_no_clone_reason_detection():
    assert gitclaim.is_no_clone_nack_reason(
        "worktree-create-failed:no-clone (FR #6240)"
    )
    assert gitclaim.is_no_clone_nack_reason("worktree-create-failed:no-clone")
    assert gitclaim.is_deterministic_nack_reason(
        "worktree-create-failed:no-clone (FR #6240)"
    )
    assert not gitclaim.is_no_clone_nack_reason("worktree-create-failed:git-worktree")
    assert not gitclaim.is_no_clone_nack_reason("busy")


def test_nack_then_bored_7s_no_reoffer_same_seat_other_seat_gets_it(tmp_path, monkeypatch):
    """AC3: replay of redqueen log — NACK then !bored ~7s later must not re-offer."""
    home = _home(tmp_path, monkeypatch)
    now = time.time()
    row = _row(
        REPO,
        "MRB",
        689,
        offered_to=SEAT_A,
        offered_ts=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    result = shop_listen.handle_shop_worker_line(
        home,
        nick=SEAT_A,
        channel="#redqueen",
        body=f"NACK MRB {REPO}#689 worktree-create-failed:no-clone (FR #6240)",
        post_fn=lambda _p: 204,
    )
    assert result.get("handled")
    assert result.get("deterministic_nack") or result.get("no_clone_repo")
    held = gitclaim.load_unaccepted(home)[0]
    assert held.get("deterministic_nack_until")
    assert gitclaim.seat_blocked_for_no_clone_repo(home, SEAT_A, REPO)

    # 7 seconds later — seat !bored must not get the same key.
    st_a, job_a = gitclaim.offer_focus_top(home, SEAT_A, "#redqueen", now=now + 7)
    assert st_a == "empty" and job_a is None

    st_b, job_b = gitclaim.offer_focus_top(home, SEAT_B, "#flamingo", now=now + 7)
    assert st_b == "ok" and job_b is not None
    assert job_b["offered_to"] == SEAT_B
    assert str(job_b.get("id")) == "#689"


def test_fix_key_no_clone_same_cooldown(tmp_path, monkeypatch):
    """AC4: FIX key form covered by the same cooldown + repo block."""
    home = _home(tmp_path, monkeypatch)
    now = time.time()
    row = _row(TORAY, "FIX", 12, offered_to=SEAT_A)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    shop_listen.handle_shop_worker_line(
        home,
        nick=SEAT_A,
        channel="#redqueen",
        body=f"NACK FIX {TORAY}#12 worktree-create-failed:no-clone (FR #6240)",
        post_fn=lambda _p: 204,
    )
    held = gitclaim.load_unaccepted(home)[0]
    assert held.get("deterministic_nack_until")
    assert gitclaim.seat_blocked_for_no_clone_repo(home, SEAT_A, TORAY)
    assert gitclaim.offer_focus_top(home, SEAT_A, "#redqueen", now=now + 10)[0] == "empty"
    st_b, job_b = gitclaim.offer_focus_top(home, SEAT_B, "#flamingo", now=now + 10)
    assert st_b == "ok" and job_b is not None


def test_no_clone_blocks_all_jobs_for_repo_until_join(tmp_path, monkeypatch):
    """AC2: no-clone for one issue blocks every job for that repo on the seat."""
    home = _home(tmp_path, monkeypatch)
    now = time.time()
    rows = [
        _row(REPO, "MRB", 689, offered_to=SEAT_A),
        _row(REPO, "MRB", 692),
        _row(TORAY, "MRB", 12),
    ]
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": rows, "accepted": [], "done": []},
    )
    shop_listen.handle_shop_worker_line(
        home,
        nick=SEAT_A,
        channel="#redqueen",
        body=f"NACK MRB {REPO}#689 worktree-create-failed:no-clone (FR #6240)",
        post_fn=lambda _p: 204,
    )
    # Same seat must not get #692 (other issue, same repo) either.
    st_a, job_a = gitclaim.offer_focus_top(home, SEAT_A, "#redqueen", now=now + 10)
    assert st_a == "ok" and job_a is not None
    assert str(job_a.get("repo")).lower().endswith("toray")
    assert str(job_a.get("id")) == "#12"

    # Alias form of the blocked repo also blocked.
    assert gitclaim.seat_blocked_for_no_clone_repo(home, SEAT_A, REPO_ALIAS)

    # JOIN / hello clears the repo block so a later offer of #692 can succeed
    # once the per-row deterministic cooldown also expires.
    tracker = chan_workers.WorkerTracker(home, post_fn=lambda _p: 204)
    tracker.on_join(SEAT_A, "#redqueen")
    assert not gitclaim.seat_blocked_for_no_clone_repo(home, SEAT_A, REPO)

    later = now + float(gitclaim.GIVEUP_COOLDOWN_S) + 5
    # Isolate #692 so model/focus noise from the other rows cannot hide the unblock.
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [_row(REPO, "MRB", 692)],
            "accepted": [],
            "done": [],
        },
    )
    st2, job2 = gitclaim.offer_focus_top(home, SEAT_A, "#redqueen", now=later)
    assert st2 == "ok" and job2 is not None
    assert str(job2.get("id")) == "#692"


def test_stamp_matches_alias_repo_spelling(tmp_path, monkeypatch):
    """Row stored under alias still receives deterministic_nack_until (FR #8153 gap)."""
    home = _home(tmp_path, monkeypatch)
    now = time.time()
    row = _row(REPO_ALIAS, "MRB", 691, offered_to=SEAT_A)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    shop_listen.handle_shop_worker_line(
        home,
        nick=SEAT_A,
        channel="#redqueen",
        body=f"NACK MRB {REPO}#691 worktree-create-failed:no-clone (FR #6240)",
        post_fn=lambda _p: 204,
    )
    held = gitclaim.load_unaccepted(home)[0]
    assert held.get("deterministic_nack_until")
    assert gitclaim.offer_focus_top(home, SEAT_A, "#redqueen", now=now + 10)[0] == "empty"
