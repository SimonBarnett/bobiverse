# -*- coding: utf-8 -*-
"""FR #3205: offer order = focus → MRB < UAT < FR → lowest number; next FR when can't MRB;
zero GitHub on !bored when precompute is fresh.
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
    """Chair home with registered machines + live seats (BOB_DIGEST_HOME for seat roster)."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    # Clear seat roster cache so the new registry is visible.
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"marchhare", "ionos", "flamingo"})
    digest = bobreport.empty_digest()
    for mid, pids in (
        ("marchhare", ("35600", "35601", "35602", "35603", "35604")),
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
        "seq": seq if seq is not None else num + 1000,  # seq deliberately NOT number order
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


def _offer_ids(home: Path, seats: list[str]) -> list[str]:
    """Successive offers to fresh seats; stamp each pick as accepted so the next is free."""
    out = []
    for nick in seats:
        st, job = gitclaim.offer_focus_top(home, nick, f"#{nick.split('-')[0]}")
        assert st == "ok" and job is not None, (st, job, nick)
        out.append(job["id"])
        # Accept so the next offer does not rebroadcast the same pin.
        gitclaim.accept_offer(home, nick, job) if hasattr(gitclaim, "accept_offer") else None
        with gitclaim._lock(home):
            doc = gitclaim._load_queue_unlocked(home)
            # Move offered row to accepted (minimal accept).
            kept = []
            for r in doc.get("unaccepted") or []:
                if (
                    str(r.get("repo")) == str(job.get("repo"))
                    and str(r.get("task")) == str(job.get("task"))
                    and str(r.get("id")) == str(job.get("id"))
                ):
                    r = dict(r)
                    r["nick"] = nick
                    r["accepted_ts"] = gitclaim._utc_now()
                    doc.setdefault("accepted", []).append(r)
                else:
                    kept.append(r)
            doc["unaccepted"] = kept
            gitclaim._write_queue(gitclaim.queue_path(home), doc)
    return out


def test_fr3205_mixed_one_repo_order(home: Path):
    """MRB #5, MRB #12, UAT #0, FR #3, FR #9 — lowest number within kind."""
    repo = "SimonBarnett/bobiverse"
    _queue(
        home,
        [
            _row(repo, "MRB", 12, seq=1),
            _row(repo, "MRB", 5, seq=2),
            _row(repo, "FR", 9, seq=3),
            _row(repo, "FR", 3, seq=4),
            _row(repo, "UAT", 0, seq=5, title="repo UAT", repo_uat=True),
        ],
    )
    fi.handle_focus_cmd(home, repo)
    got = [r["id"] for r in gitclaim.ordered_unaccepted(home)]
    assert got == ["#5", "#12", "#0", "#3", "#9"], got
    seats = [f"marchhare-3560{i}" for i in range(5)]
    # Ensure extra seats exist in digest for successive offers.
    assert _offer_ids(home, seats) == ["#5", "#12", "#0", "#3", "#9"]


def test_fr3205_focus_first_across_repos(home: Path):
    """a-search p1 FR beats bobiverse p2 MRB (Simon-confirmed focus-first)."""
    _queue(
        home,
        [
            _row("SimonBarnett/bobiverse", "MRB", 3000, seq=1),
            _row("SimonBarnett/a-search", "FR", 7, seq=2),
        ],
    )
    fi.handle_focus_cmd(home, "1 SimonBarnett/a-search")
    fi.handle_focus_cmd(home, "2 SimonBarnett/bobiverse")
    st, job = gitclaim.offer_focus_top(home, "marchhare-35600", "#marchhare")
    assert st == "ok" and job["id"] == "#7" and "a-search" in job["repo"]


def test_fr3205_same_priority_interleave_by_kind_then_number(home: Path):
    """Same priority: MRB before FR, lowest number; repo name only as final tie-break (not focus ts)."""
    # Older focus timestamp on agentic_fomprep must NOT beat a-search MRB of same priority.
    _queue(
        home,
        [
            _row("SimonBarnett/a-search", "FR", 10, seq=1),
            _row("SimonBarnett/a-search", "MRB", 20, seq=2),
            _row("agentic_fomprep", "FR", 5, seq=3),
            _row("agentic_fomprep", "MRB", 8, seq=4),
        ],
    )
    fi.handle_focus_cmd(home, "1 agentic_fomprep")
    # Force older ts on agentic_fomprep, newer on a-search (legacy bug used ts as tie-break).
    doc = fi.load_focus(home)
    doc["repos"]["agentic_fomprep"]["ts"] = "2026-10-07T09:17:00Z"
    doc["repos"]["SimonBarnett/a-search"] = {
        "priority": 1,
        "label": "high",
        "ts": "2026-10-07T18:37:00Z",
    }
    fi.save_focus(home, doc)
    got = [(r["repo"], r["task"], r["id"]) for r in gitclaim.ordered_unaccepted(home)]
    # Both p1: all MRBs (by number) then all FRs (by number); repo name breaks ties.
    assert got[0][1] == "MRB" and got[1][1] == "MRB"
    assert got[2][1] == "FR" and got[3][1] == "FR"
    mrb_nums = [int(x[2].lstrip("#")) for x in got if x[1] == "MRB"]
    fr_nums = [int(x[2].lstrip("#")) for x in got if x[1] == "FR"]
    assert mrb_nums == sorted(mrb_nums)
    assert fr_nums == sorted(fr_nums)


def test_fr3205_skips_seat_relative(home: Path):
    """Gave-up MRB #5 + needs-human FR #3 → this seat gets MRB #12 then FR #9."""
    repo = "SimonBarnett/bobiverse"
    me, other = "marchhare-35600", "marchhare-35601"
    rows = [
        _row(repo, "MRB", 5, seq=1),
        _row(repo, "MRB", 12, seq=2),
        _row(repo, "FR", 3, seq=3, needs_human=True),
        _row(repo, "FR", 9, seq=4),
    ]
    rows[0]["giveup_seats"] = me
    _queue(home, rows)
    fi.handle_focus_cmd(home, repo)
    st, j1 = gitclaim.offer_focus_top(home, me, "#marchhare")
    assert st == "ok" and j1["id"] == "#12"
    # Accept #12
    with gitclaim._lock(home):
        doc = gitclaim._load_queue_unlocked(home)
        doc["unaccepted"] = [r for r in doc["unaccepted"] if r.get("id") != "#12"]
        doc.setdefault("accepted", []).append(dict(j1))
        gitclaim._write_queue(gitclaim.queue_path(home), doc)
    st, j2 = gitclaim.offer_focus_top(home, me, "#marchhare")
    assert st == "ok" and j2["id"] == "#9"
    # Other seat still gets MRB #5 first
    st, j3 = gitclaim.offer_focus_top(home, other, "#marchhare")
    assert st == "ok" and j3["id"] == "#5"


def test_fr3205_cant_mrb_gets_next_fr(home: Path):
    """Own PR as MRB #40 (self-review blocked) → !bored returns FR #8, never empty."""
    repo = "SimonBarnett/bobiverse"
    me, other = "marchhare-35600", "marchhare-35601"
    mrb = _row(repo, "MRB", 40, seq=1)
    mrb["author_seat"] = me
    mrb["implementer_seat"] = me
    _queue(home, [mrb, _row(repo, "FR", 20, seq=2), _row(repo, "FR", 8, seq=3)])
    fi.handle_focus_cmd(home, repo)
    st, job = gitclaim.offer_focus_top(home, me, "#marchhare")
    assert st == "ok", st
    assert job is not None and job["id"] == "#8" and job["task"] == "FR"
    st2, job2 = gitclaim.offer_focus_top(home, other, "#marchhare")
    assert st2 == "ok" and job2["id"] == "#40"


def test_fr3205_webhook_lower_number_sorts_before_seq(home: Path):
    """Webhook-appended FR #4 (high seq) sorts before FR #6 when ordering by number."""
    repo = "SimonBarnett/a-search"
    _queue(home, [_row(repo, "FR", 6, seq=10), _row(repo, "FR", 4, seq=999)])
    fi.handle_focus_cmd(home, repo)
    got = [r["id"] for r in gitclaim.ordered_unaccepted(home)]
    assert got == ["#4", "#6"]
    st, job = gitclaim.offer_focus_top(home, "marchhare-35600", "#marchhare")
    assert st == "ok" and job["id"] == "#4"


def test_fr3205_fallback_obeys_kind_and_number(home: Path):
    """Fallback path (when focus walk yields nothing for this seat) still MRB before FR."""
    repo = "SimonBarnett/bobiverse"
    me = "marchhare-35600"
    # Seat gave up the lowest MRB; next eligible must still be MRB #9 before FR #3.
    mrb5 = _row(repo, "MRB", 5, seq=1)
    mrb5["giveup_seats"] = me
    _queue(
        home,
        [
            mrb5,
            _row(repo, "FR", 3, seq=2),
            _row(repo, "MRB", 9, seq=3),
        ],
    )
    fi.handle_focus_cmd(home, repo)
    st, job = gitclaim.offer_focus_top(home, me, "#marchhare")
    assert st == "ok" and job["task"] == "MRB" and job["id"] == "#9"


def test_fr3205_precompute_bored_zero_github(home: Path):
    """Fresh precompute → !bored makes zero GitHub calls."""
    repo = "SimonBarnett/a-search"
    rows = [_row(repo, "FR", i, seq=i + 50) for i in (9, 3, 7)]
    _queue(home, rows)
    fi.handle_focus_cmd(home, repo)
    gitclaim.rebuild_offer_precompute(home)
    calls = {"n": 0}

    def boom(*_a, **_k):
        calls["n"] += 1
        raise AssertionError("GitHub must not be called on !bored with fresh precompute")

    st, job = gitclaim.offer_focus_top(
        home,
        "marchhare-35600",
        "#marchhare",
        pr_exists=boom,
        is_pull=boom,
        issue_open=boom,
    )
    assert st == "ok" and job is not None
    assert job["id"] == "#3"
    assert calls["n"] == 0
