"""FR #4422: resync skip logging + rate-limit retry; !assign enqueue; done guard; unpin #4343."""
from __future__ import annotations

import time
from pathlib import Path

import bobreport
import chair_health as ch
import gitclaim
import github_api_budget as gab
import shop_listen

REPO = "SimonBarnett/bobiverse"
NICK = "marchhare-23068"


def _queue(home: Path, unaccepted=None, accepted=None, done=None) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": list(unaccepted or []),
            "accepted": list(accepted or []),
            "done": list(done or []),
        },
    )


def _register(home: Path, monkeypatch) -> None:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["marchhare"]}', encoding="utf-8"
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    doc = bobreport.empty_digest()
    doc["machines"]["marchhare"] = {
        "id": "marchhare",
        "online": True,
        "working_on": "",
        "worker_list": [{"nick": NICK, "state": "idle", "work": ""}],
        "workers": {"23068": {"pid": "23068", "nick": NICK, "state": "idle"}},
    }
    bobreport.save_digest(home, doc)


# --------------------------------------------------------------------------- 1. rate-limit retry / skip log
def test_fr4422_rate_limit_clears_after_reset(tmp_path: Path):
    clock = {"t": 1_000_000.0}
    logs: list[str] = []
    bud = gab.GithubApiBudget(
        tmp_path, budget_per_hour=1000, floor=500, clock=lambda: clock["t"], log=logs.append
    )
    bud.rate_remaining = 0
    bud.rate_reset = clock["t"] + 60
    bud.used = 10
    assert bud.allow("reconcile", essential=False) is False
    assert any("backoff" in ln for ln in logs)
    clock["t"] = bud.rate_reset + 1
    assert bud.allow("reconcile", essential=False) is True
    assert bud.rate_remaining is None


def test_fr4422_resync_cycle_logs_skip_reason(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JEEVES_RESYNC_REPOS", "SimonBarnett/bobiverse")
    logs: list[str] = []
    bud = gab.GithubApiBudget(tmp_path, budget_per_hour=2, floor=500, log=logs.append)
    bud.used = 2
    bud.rate_remaining = 0
    bud.rate_reset = time.time() + 120
    bud._persist_budget()
    out = ch.resync_cycle(
        tmp_path,
        token="tok",
        ignored=[],
        budget=bud,
        essential=False,
        log=logs.append,
        owners={"simonbarnett"},
    )
    assert out.get("note") == "budget-backoff"
    assert out.get("skip_reason")
    assert "rate-limit" in out["skip_reason"] or "hourly-budget" in out["skip_reason"]
    assert any("github-resync skipped" in ln for ln in logs)
    assert out.get("rate_reset") is not None


def test_fr4422_chair_jobs_pulls_resync_forward_after_backoff(tmp_path: Path):
    class Clock:
        def __init__(self):
            self.t = 100_000.0

        def __call__(self):
            return self.t

    logs: list[str] = []
    clk = Clock()
    # fetch_json=None so resync_cycle hits the real budget gate (FR #4422).
    j = ch.ChairJobs(
        tmp_path,
        tmp_path,
        log=logs.append,
        announce=lambda s: None,
        http=lambda *a, **k: 200,
        fetch_json=None,
        token_loader=lambda: ("tok", "file:x"),
        ignored_loader=lambda: [],
        clock=clk,
        sleep=lambda s: None,
        spawn=False,
        owners={"simonbarnett"},
    )
    j.api_budget.used = j.api_budget.budget_per_hour
    j.api_budget.rate_remaining = 0
    j.api_budget.rate_reset = clk.t + 90
    j.api_budget._persist_budget()
    j.next_resync = clk.t
    j.next_probe = clk.t + 10_000
    j.next_merge_on_green = clk.t + 10_000
    j._startup_resync_done = True
    j.tick()
    assert j.last_resync.get("note") == "budget-backoff"
    assert j.next_resync <= clk.t + 91
    assert any("retry scheduled" in ln for ln in logs)
    assert any("github-resync skipped" in ln for ln in logs)


# --------------------------------------------------------------------------- 2. !assign enqueue
def test_fr4422_assign_enqueues_open_fr_missing_from_queue(tmp_path: Path, monkeypatch):
    _register(tmp_path, monkeypatch)
    _queue(tmp_path, unaccepted=[])
    monkeypatch.setattr(gitclaim, "worker_working_on", lambda h, n: "")
    monkeypatch.setattr(gitclaim, "live_seat_nicks", lambda h: {NICK})
    monkeypatch.setattr(gitclaim, "free_seat_nicks", lambda h, live: {NICK})
    monkeypatch.setattr(gitclaim, "seat_open_job", lambda *a, **k: "")

    def fake_fetch(repo, num):
        assert str(num).lstrip("#") == "2230"
        return {
            "number": 2230,
            "title": "open product FR",
            "body": "fix",
            "state": "open",
            "labels": [{"name": "bug"}],
        }

    st, job = gitclaim.assign_row(
        tmp_path,
        NICK,
        "SimonBarnett/a-search",
        "FR",
        "#2230",
        fetch_issue=fake_fetch,
        issue_open=lambda *a, **k: True,
    )
    assert st == "ok", job
    assert isinstance(job, dict)
    assert str(job.get("id")) == "#2230"
    assert str(job.get("offered_to")) == NICK
    rows = gitclaim.load_unaccepted(tmp_path)
    assert any(str(r.get("id")) == "#2230" for r in rows)


def test_fr4422_assign_refuses_closed_issue_not_in_queue(tmp_path: Path, monkeypatch):
    _register(tmp_path, monkeypatch)
    _queue(tmp_path, unaccepted=[])
    monkeypatch.setattr(gitclaim, "worker_working_on", lambda h, n: "")
    monkeypatch.setattr(gitclaim, "live_seat_nicks", lambda h: {NICK})
    monkeypatch.setattr(gitclaim, "free_seat_nicks", lambda h, live: {NICK})
    monkeypatch.setattr(gitclaim, "seat_open_job", lambda *a, **k: "")

    def fake_fetch(repo, num):
        return {
            "number": int(str(num).lstrip("#")),
            "title": "closed",
            "body": "",
            "state": "closed",
            "labels": [],
        }

    st, why = gitclaim.assign_row(
        tmp_path,
        NICK,
        REPO,
        "FR",
        "#9999",
        fetch_issue=fake_fetch,
    )
    assert st == "refused"
    assert "not in the unaccepted queue" in str(why)


# --------------------------------------------------------------------------- 3. done guard
def test_fr4422_complete_fr_without_pull_url_refused(tmp_path: Path, monkeypatch):
    _register(tmp_path, monkeypatch)
    row = {
        "repo": REPO,
        "task": "FR",
        "id": "#4422",
        "nick": NICK,
        "accepted_ts": "2026-10-16T12:00:00Z",
    }
    _queue(tmp_path, accepted=[row])
    st, job = shop_listen.complete_job_by_ref(
        tmp_path, nick=NICK, repo=REPO, task="FR", ident="#4422", result="done", url=""
    )
    assert st == "refused"
    assert job is None
    assert len(gitclaim.load_queue(tmp_path)["accepted"]) == 1


def test_fr4422_complete_fr_with_pull_url_ok(tmp_path: Path, monkeypatch):
    _register(tmp_path, monkeypatch)
    row = {
        "repo": REPO,
        "task": "FR",
        "id": "#4422",
        "nick": NICK,
        "accepted_ts": "2026-10-16T12:00:00Z",
    }
    _queue(tmp_path, accepted=[row])
    url = f"https://github.com/{REPO}/pull/4425"
    st, job = shop_listen.complete_job_by_ref(
        tmp_path, nick=NICK, repo=REPO, task="FR", ident="#4422", result=url, url=url
    )
    assert st == "ok"
    assert job is not None
    done = gitclaim.load_queue(tmp_path).get("done") or []
    assert any(str(r.get("id")) == "#4422" for r in done)


def test_fr4422_stale_busy_requeues_without_pull_evidence(tmp_path: Path, monkeypatch):
    _register(tmp_path, monkeypatch)
    doc = bobreport.load_digest(tmp_path)
    doc["machines"]["marchhare"]["working_on"] = "bobiverse FR #2340"
    doc["machines"]["marchhare"]["worker_list"][0]["state"] = "doing"
    doc["machines"]["marchhare"]["worker_list"][0]["work"] = "bobiverse FR #2340"
    bobreport.save_digest(tmp_path, doc)
    now = time.time()
    old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 8 * 3600))
    _queue(
        tmp_path,
        accepted=[
            {
                "repo": REPO,
                "task": "FR",
                "id": "#2340",
                "nick": NICK,
                "accepted_ts": old,
                "ts": old,
            }
        ],
    )
    assert gitclaim.release_stale_busy(tmp_path, NICK, now)
    q = gitclaim.load_queue(tmp_path)
    assert q["accepted"] == []
    assert not any(str(r.get("id")) == "#2340" for r in (q.get("done") or []))
    assert any(
        str(r.get("id")) == "#2340" and "requeue:STALE_BUSY" in str(r.get("reconcile") or "")
        for r in (q.get("unaccepted") or [])
    )


# --------------------------------------------------------------------------- 4. unpin #4343
def test_fr4422_unpin_4343_hard_and_missing_needs_ionos_title():
    assert ("simonbarnett/bobiverse", "#4343") in gitclaim._REQUIRE_MACHINE_ISSUE_UNPINS
    # Meta title that used to self-pin via needs-ionos cue.
    title = "chair offered ionos-only FR #4340 to marchhare (missing needs-ionos stamp)"
    assert (
        gitclaim.infer_require_machine(
            title=title,
            body="No needs-ionos stamp was present.",
            repo=REPO,
            ident="#4343",
        )
        == ""
    )
    row = {
        "repo": REPO,
        "task": "FR",
        "id": "#4343",
        "title": title,
        "body": "Fix require_machine cues.",
        "require_machine": "ionos",
    }
    assert gitclaim.row_require_machine(row) == ""
    gitclaim._stamp_require_machine(row)
    assert str(row.get("require_machine") or "").lower() in {"any", "*", "none", "-"}


def test_fr4422_needs_ionos_label_still_pins_bobiverse():
    """FR #4512: bobiverse soft title cues do not pin; needs-ionos label still does."""
    assert (
        gitclaim.infer_require_machine(
            title="recycle ircJeeves after allowlist change",
            body="",
            labels=("needs-ionos",),
            repo=REPO,
            ident="#999",
        )
        == "ionos"
    )
    assert (
        gitclaim.infer_require_machine(
            title="needs-ionos: recycle ircJeeves after allowlist change",
            body="",
            labels=(),
            repo=REPO,
            ident="#999",
        )
        == ""
    )
