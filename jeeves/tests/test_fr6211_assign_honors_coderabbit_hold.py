"""FR #6211: ordinary !assign honors automatic MRB CodeRabbit hold.

offer_focus_top / offer_top already call fuel_chain.apply_mrb_coderabbit_gate.
assign_row must refuse the same pending current-head wait with an actionable
reason and without stamping offered_to. needs_human remains the documented
manual exception. Empty-offer diagnostics expose coderabbit_hold + row.
"""
from __future__ import annotations

import re
from pathlib import Path

import bobreport
import fuel_chain
import gitclaim
import registered_machines


REPO = "SimonBarnett/bobiverse"
NICK = "redqueen-4836"
AUTHOR = "redqueen-15544"
NOW = 1_700_000_000.0


def _machine_from_seat(nick: str) -> str:
    m = re.match(r"^(.+)-(\d+)$", (nick or "").strip().lower())
    return m.group(1) if m else (nick or "").strip().lower()


def _digest_home(tmp_path: Path, monkeypatch, nicks: list[str]) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    machines = sorted({_machine_from_seat(n) for n in nicks if n})
    registered_machines.save_registered(tmp_path, set(machines) or {"redqueen"})
    digest = bobreport.empty_digest()
    for mid in machines or ["redqueen"]:
        digest["machines"][mid] = bobreport._empty_machine(mid)
        digest["machines"][mid]["worker_list"] = [
            {"nick": n, "state": "idle"}
            for n in nicks
            if _machine_from_seat(n) == mid
        ]
    bobreport.save_digest(tmp_path, digest)
    return tmp_path


def _mrb(
    num: str = "6210",
    *,
    since: float = NOW,
    stamp: str = "pending",
    head: str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    author: str = AUTHOR,
    repo: str = REPO,
) -> dict:
    return {
        "repo": repo,
        "task": "MRB",
        "id": "#%s" % num,
        "url": "https://github.com/%s/pull/%s" % (repo, num),
        "title": "fix fr",
        "line": "MRB %s#%s" % (repo, num),
        "seq": int(num),
        "state": "open",
        "author_seat": author,
        "implementer_seat": author,
        "coderabbit": stamp,
        "coderabbit_wait_since": since,
        "coderabbit_head_sha": head,
        "head_sha": head,
        "review": "full",
    }


def _queue(home: Path, rows: list[dict]) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": rows, "accepted": [], "done": [], "workers": {}},
    )


def _no_cr(_repo: str, _num: str):
    return {"ready": False, "failed": False, "activity": True}


def _ready_cr(_repo: str, _num: str):
    return {"ready": True, "failed": False, "activity": True}


def test_assign_refuses_pending_coderabbit_before_timeout(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    monkeypatch.setenv("BOB_CODERABBIT_WAIT_MIN", "12")
    monkeypatch.setattr(fuel_chain, "repo_has_coderabbit_yaml", lambda *a, **k: True)
    home = _digest_home(tmp_path, monkeypatch, [NICK, AUTHOR])
    row = _mrb(since=NOW)
    _queue(home, [row])
    monkeypatch.setattr(gitclaim, "worker_working_on", lambda *a, **k: "")
    monkeypatch.setattr(gitclaim, "seat_open_job", lambda *a, **k: "")

    st, why = gitclaim.assign_row(
        home,
        NICK,
        REPO,
        "MRB",
        "#6210",
        now=NOW + 11 * 60 + 27,
        pr_exists=lambda r, n: True,
        coderabbit_lookup=_no_cr,
    )
    assert st == "refused", why
    assert "coderabbit_hold" in str(why).lower()
    assert "6210" in str(why)
    assert "rem_s=" in str(why) or "remaining" in str(why).lower()
    assert "age_s=" in str(why) or "age=" in str(why).lower()

    q = gitclaim._load_queue_unlocked(home)
    held = q["unaccepted"][0]
    assert not held.get("offered_to"), held
    assert str(held.get("coderabbit") or "") == "pending"


def test_offer_and_assign_agree_while_pending(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    monkeypatch.setenv("BOB_CODERABBIT_WAIT_MIN", "12")
    monkeypatch.setattr(fuel_chain, "repo_has_coderabbit_yaml", lambda *a, **k: True)
    home = _digest_home(tmp_path, monkeypatch, [NICK, AUTHOR])
    _queue(home, [_mrb(since=NOW)])
    monkeypatch.setattr(gitclaim, "worker_working_on", lambda *a, **k: "")
    monkeypatch.setattr(gitclaim, "seat_open_job", lambda *a, **k: "")
    monkeypatch.setattr(fuel_chain, "lookup_coderabbit_state", lambda *a, **k: _no_cr("", ""))

    st_o, job_o = gitclaim.offer_focus_top(
        home, NICK, "#redqueen", now=NOW + 60, pr_exists=lambda r, n: True
    )
    assert st_o == "empty" and job_o is None

    st_a, why = gitclaim.assign_row(
        home,
        NICK,
        REPO,
        "MRB",
        "#6210",
        now=NOW + 60,
        pr_exists=lambda r, n: True,
        coderabbit_lookup=_no_cr,
    )
    assert st_a == "refused"
    assert "coderabbit_hold" in str(why).lower()


def test_assign_allows_after_timeout_stamp(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    monkeypatch.setenv("BOB_CODERABBIT_WAIT_MIN", "12")
    monkeypatch.setattr(fuel_chain, "repo_has_coderabbit_yaml", lambda *a, **k: True)
    home = _digest_home(tmp_path, monkeypatch, [NICK, AUTHOR])
    _queue(home, [_mrb(since=NOW)])
    monkeypatch.setattr(gitclaim, "worker_working_on", lambda *a, **k: "")
    monkeypatch.setattr(gitclaim, "seat_open_job", lambda *a, **k: "")

    st, job = gitclaim.assign_row(
        home,
        NICK,
        REPO,
        "MRB",
        "#6210",
        now=NOW + 12 * 60 + 1,
        pr_exists=lambda r, n: True,
        coderabbit_lookup=_no_cr,
    )
    assert st == "ok", job
    assert job.get("offered_to") == NICK
    assert job.get("coderabbit") == "timeout"


def test_assign_allows_ready_current_head(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    monkeypatch.setattr(fuel_chain, "repo_has_coderabbit_yaml", lambda *a, **k: True)
    home = _digest_home(tmp_path, monkeypatch, [NICK, AUTHOR])
    _queue(home, [_mrb(stamp="ready")])
    monkeypatch.setattr(gitclaim, "worker_working_on", lambda *a, **k: "")
    monkeypatch.setattr(gitclaim, "seat_open_job", lambda *a, **k: "")

    st, job = gitclaim.assign_row(
        home,
        NICK,
        REPO,
        "MRB",
        "#6210",
        now=NOW + 30,
        pr_exists=lambda r, n: True,
        coderabbit_lookup=_ready_cr,
    )
    assert st == "ok", job
    assert job.get("coderabbit") == "ready"


def test_assign_old_head_ready_does_not_clear_new_head(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    monkeypatch.setenv("BOB_CODERABBIT_WAIT_MIN", "12")
    monkeypatch.setattr(fuel_chain, "repo_has_coderabbit_yaml", lambda *a, **k: True)
    home = _digest_home(tmp_path, monkeypatch, [NICK, AUTHOR])
    old = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    new = "cccccccccccccccccccccccccccccccccccccccc"
    row = _mrb(stamp="ready", head=new)
    row["coderabbit_head_sha"] = old  # ready stamped for older SHA
    _queue(home, [row])
    monkeypatch.setattr(gitclaim, "worker_working_on", lambda *a, **k: "")
    monkeypatch.setattr(gitclaim, "seat_open_job", lambda *a, **k: "")

    st, why = gitclaim.assign_row(
        home,
        NICK,
        REPO,
        "MRB",
        "#6210",
        now=NOW + 30,
        pr_exists=lambda r, n: True,
        coderabbit_lookup=_no_cr,
    )
    assert st == "refused", why
    assert "coderabbit_hold" in str(why).lower()


def test_assign_failed_timeout_absent_off_remain_offerable(tmp_path, monkeypatch):
    home = _digest_home(tmp_path, monkeypatch, [NICK, AUTHOR])
    monkeypatch.setattr(gitclaim, "worker_working_on", lambda *a, **k: "")
    monkeypatch.setattr(gitclaim, "seat_open_job", lambda *a, **k: "")
    monkeypatch.setattr(fuel_chain, "repo_has_coderabbit_yaml", lambda *a, **k: True)

    # failed: same-head failed stamp clears the gate without waiting.
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    _queue(home, [_mrb(num="7001", stamp="failed")])
    st, job = gitclaim.assign_row(
        home,
        NICK,
        REPO,
        "MRB",
        "#7001",
        now=NOW + 10,
        pr_exists=lambda r, n: True,
        coderabbit_lookup=_no_cr,
    )
    assert st == "ok", job
    assert job.get("coderabbit") == "failed"

    # timeout after wait window.
    monkeypatch.setenv("BOB_CODERABBIT_WAIT_MIN", "12")
    _queue(home, [_mrb(num="7002", stamp="pending", since=NOW)])
    st, job = gitclaim.assign_row(
        home,
        NICK,
        REPO,
        "MRB",
        "#7002",
        now=NOW + 12 * 60 + 5,
        pr_exists=lambda r, n: True,
        coderabbit_lookup=_no_cr,
    )
    assert st == "ok", job
    assert job.get("coderabbit") == "timeout"

    # absent: no .coderabbit.yaml on the repo.
    monkeypatch.setattr(fuel_chain, "repo_has_coderabbit_yaml", lambda *a, **k: False)
    _queue(home, [_mrb(num="7003", stamp="pending", since=NOW)])
    st, job = gitclaim.assign_row(
        home,
        NICK,
        REPO,
        "MRB",
        "#7003",
        now=NOW + 10,
        pr_exists=lambda r, n: True,
        coderabbit_lookup=_no_cr,
    )
    assert st == "ok", job
    assert job.get("coderabbit") == "absent"

    # off: stage disabled.
    monkeypatch.delenv("BOB_FUEL_CODERABBIT", raising=False)
    monkeypatch.setattr(fuel_chain, "repo_has_coderabbit_yaml", lambda *a, **k: True)
    _queue(home, [_mrb(num="7004", stamp="pending", since=NOW)])
    st, job = gitclaim.assign_row(
        home,
        NICK,
        REPO,
        "MRB",
        "#7004",
        now=NOW + 10,
        pr_exists=lambda r, n: True,
        coderabbit_lookup=_no_cr,
    )
    assert st == "ok", job
    assert job.get("coderabbit") == "off"


def test_needs_human_assign_exception_preserved(tmp_path, monkeypatch):
    """FR #4336 / #6211: needs_human may still be handed out via ordinary !assign."""
    monkeypatch.delenv("BOB_FUEL_CODERABBIT", raising=False)
    home = _digest_home(tmp_path, monkeypatch, [NICK, AUTHOR])
    row = _mrb(stamp="off")
    row["needs_human"] = True
    _queue(home, [row])
    monkeypatch.setattr(gitclaim, "worker_working_on", lambda *a, **k: "")
    monkeypatch.setattr(gitclaim, "seat_open_job", lambda *a, **k: "")

    st_o, job_o = gitclaim.offer_focus_top(
        home, NICK, "#redqueen", now=NOW + 10, pr_exists=lambda r, n: True
    )
    assert st_o == "empty" and job_o is None

    st, job = gitclaim.assign_row(
        home,
        NICK,
        REPO,
        "MRB",
        "#6210",
        now=NOW + 10,
        pr_exists=lambda r, n: True,
        coderabbit_lookup=_no_cr,
    )
    assert st == "ok", job
    assert job.get("offered_to") == NICK


def test_summarize_empty_offer_reports_coderabbit_hold(tmp_path, monkeypatch):
    import time as _time

    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    monkeypatch.setenv("BOB_CODERABBIT_WAIT_MIN", "12")
    monkeypatch.setattr(fuel_chain, "repo_has_coderabbit_yaml", lambda *a, **k: True)
    home = _digest_home(tmp_path, monkeypatch, [NICK, AUTHOR])
    # summarize_empty_offer uses wall clock; keep wait_since recent.
    _queue(home, [_mrb(since=_time.time() - 60)])
    stats = gitclaim.summarize_empty_offer(home, NICK)
    assert int(stats.get("coderabbit_hold") or 0) >= 1
    assert "6210" in str(stats.get("coderabbit_hold_row") or "")
    detail = gitclaim.format_empty_offer_detail(NICK, stats)
    assert "coderabbit_hold=" in detail
    assert "6210" in detail


def test_priority_bob_held_allows_lower_absent(tmp_path, monkeypatch):
    """Held priority-1 Bob MRB must not look like priority inversion when absent HR work offers."""
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    monkeypatch.setenv("BOB_CODERABBIT_WAIT_MIN", "12")
    home = _digest_home(tmp_path, monkeypatch, [NICK, AUTHOR])
    import focus_ignore

    focus_ignore.handle_focus_cmd(home, "strict on")
    focus_ignore.handle_focus_cmd(home, "high SimonBarnett/bobiverse")
    focus_ignore.handle_focus_cmd(home, "medium SimonBarnett/hrsmith")
    import time as _time

    wall = _time.time()
    bob = _mrb(num="6210", since=wall - 60, stamp="pending")
    hrs = _mrb(
        num="19",
        since=wall - 60,
        stamp="absent",
        repo="SimonBarnett/hrsmith",
        author=AUTHOR,
    )
    _queue(home, [bob, hrs])

    def _yaml_for(repo: str, now=None):
        return "hrsmith" not in str(repo).lower()

    monkeypatch.setattr(fuel_chain, "repo_has_coderabbit_yaml", _yaml_for)
    monkeypatch.setattr(fuel_chain, "lookup_coderabbit_state", lambda *a, **k: _no_cr("", ""))
    monkeypatch.setattr(gitclaim, "worker_working_on", lambda *a, **k: "")
    monkeypatch.setattr(gitclaim, "seat_open_job", lambda *a, **k: "")

    st, job = gitclaim.offer_focus_top(
        home, NICK, "#redqueen", now=wall, pr_exists=lambda r, n: True
    )
    assert st == "ok" and job is not None
    assert "hrsmith" in str(job.get("repo") or "").lower()
    assert job.get("coderabbit") == "absent"

    stats = gitclaim.summarize_empty_offer(home, NICK)
    # After offer, bob row still held pending in queue; stats should name the hold.
    assert int(stats.get("coderabbit_hold") or 0) >= 1
    assert "6210" in str(stats.get("coderabbit_hold_row") or "")
