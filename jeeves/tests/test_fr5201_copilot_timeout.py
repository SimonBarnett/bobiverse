"""FR #5201: exercise timeout/failure handling through the real chair wiring."""
from __future__ import annotations

import json

import pytest

import chair_health
import copilot_dispatch as cd
import focus_ignore
import gitclaim
import shop_listen
import stall_filer


REPO = "SimonBarnett/bobiverse"


@pytest.fixture
def chair(tmp_path, monkeypatch):
    home = tmp_path / "chair"
    digest = tmp_path / "digest"
    home.mkdir()
    digest.mkdir()
    monkeypatch.setenv("BOB_DIGEST_HOME", str(digest))
    # FR #5267 / #5186: dispatch needs an allowance file and high focus.
    (digest / "copilot-allowance.json").write_text(
        json.dumps({"enabled": True, "remaining": 10, "state": "ok", "unlimited": True}),
        encoding="utf-8",
    )
    focus = focus_ignore.empty_focus()
    focus["repos"] = {
        REPO: {"priority": 1, "label": "high"},
        "SimonBarnett/a-search": {"priority": 1, "label": "high"},
    }
    focus_ignore.save_focus(digest, focus)
    state = {
        "now": 1_800_000_000.0,
        "task": {"state": "running"},
        "pulls": [],
        "branches": [],
        "posts": [],
        "gets": [],
        "get_code": 200,
    }
    monkeypatch.setattr(cd.time, "time", lambda: state["now"])

    def github(method, url, body=None):
        if "copilot_internal/user" in url:
            return {"quota_snapshots": {"premium_interactions": {"unlimited": True}}}, 200
        if method == "POST":
            state["posts"].append((url, body))
            return {"id": "task-1", "html_url": f"https://github.com/{REPO}/tasks/task-1"}, 201
        state["gets"].append(url)
        if "/tasks/" in url:
            return state["task"], state["get_code"]
        if "/pulls?" in url:
            return state["pulls"], state["get_code"]
        if "/git/matching-refs/" in url:
            return state["branches"], state["get_code"]
        raise AssertionError(url)

    jobs = chair_health.ChairJobs(
        home, digest, spawn=False, token_loader=lambda: ("test-token", "test"),
        clock=lambda: state["now"], announce=lambda _s: None, log=lambda _s: None,
    )
    monkeypatch.setattr(jobs, "_github_json", github)
    state["chair"] = jobs
    state["home"] = digest
    return state


def start(chair, task="FR", **extra):
    row = {
        "repo": REPO, "task": task, "id": "#5201",
        "title": "Fix timeout loop",
        "url": f"https://github.com/{REPO}/{'issues' if task == 'FR' else 'pull'}/5201",
    }
    row.update(extra)
    gitclaim._write_queue(
        gitclaim.queue_path(chair["home"]),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    chair["chair"]._copilot_tick()
    assert len(chair["posts"]) == 1
    assert gitclaim.load_accepted(chair["home"])[0]["nick"] == "copilot"


def timeout(chair):
    chair["now"] += cd.TASK_TIMEOUT_S + 1
    chair["chair"]._copilot_tick()


@pytest.mark.parametrize("task", ["FR", "FIX", "MRB"])
def test_timeout_returns_to_seats_without_redispatch(chair, task):
    start(chair, task=task)
    timeout(chair)
    home = chair["home"]
    row = gitclaim.load_unaccepted(home)[0]
    assert not gitclaim.load_accepted(home)
    assert row["giveup_seats"] == "copilot"
    assert row["giveup_count"] == 1
    assert row["cooldown_until"]
    assert row["giveup_ts"]
    assert not cd.should_dispatch(row, allowance=True)
    assert not gitclaim.row_gave_up_by(row, "ionos-123")
    assert not gitclaim.row_on_cooldown(row, chair["now"], "ionos-123")
    blocked = gitclaim.ledger_blocks(gitclaim.ledger_load(home), row, "copilot")
    if task != "MRB":
        assert blocked
    else:
        assert row["giveup_seats"] == "copilot"
    status, offered = gitclaim.offer_top(
        home, "ionos-123", "#ionos", now=chair["now"],
    )
    assert status == "ok"
    assert offered["id"] == "#5201"
    timeout(chair)
    assert len(chair["posts"]) == 1
    # The IRC ACK path can still take the returned job during Copilot's cooldown.
    status, _ = shop_listen.accept_job_by_ref(
        home, nick="ionos-123", channel="#ionos", repo=REPO, task=task, ident="#5201",
    )
    assert status == "ok"


@pytest.mark.parametrize("work", ["branch", "pr", "task", "session"])
def test_existing_work_stays_on_original_task(chair, work):
    start(chair)
    if work == "branch":
        chair["branches"] = [{"ref": "refs/heads/copilot/fr-5201-fix-timeout"}]
    elif work == "pr":
        chair["pulls"] = [{
            "user": {"login": "Copilot"},
            "head": {"ref": "copilot/fix-timeout"},
            "body": f"Closes {REPO}#5201",
        }]
    elif work == "task":
        chair["task"]["branch"] = "copilot/fix-timeout"
        chair["branches"] = [{"ref": "refs/heads/copilot/fix-timeout"}]
    else:
        chair["task"]["sessions"] = [{"pull_request_url": f"https://github.com/{REPO}/pull/5202"}]
        chair["pulls"] = [{"number": 5202}]
    timeout(chair)
    assert gitclaim.load_accepted(chair["home"])[0]["nick"] == "copilot"
    assert not gitclaim.load_unaccepted(chair["home"])
    assert cd._load_jobs(chair["home"])["jobs"][0]["task_id"] == "task-1"
    timeout(chair)
    assert len(chair["posts"]) == 1


@pytest.mark.parametrize("state", ["failed", "cancelled", "canceled", "error"])
@pytest.mark.parametrize("work", [False, True])
def test_terminal_task_checks_work_before_giveup(chair, state, work):
    start(chair)
    chair["task"] = {"state": state}
    if work:
        chair["branches"] = [{"ref": "refs/heads/copilot/fr-5201-fix-timeout"}]
    chair["now"] += 1
    chair["chair"]._copilot_tick()
    assert bool(gitclaim.load_accepted(chair["home"])) is work
    assert bool(gitclaim.load_unaccepted(chair["home"])) is not work
    assert len(chair["posts"]) == 1


def test_repeated_timeout_files_existing_all_gave_up_stall(chair, monkeypatch):
    created = []
    monkeypatch.setattr(
        stall_filer, "default_create",
        lambda title, body: created.append((title, body)) or {"number": 5300},
    )
    start(chair)
    timeout(chair)
    home = chair["home"]
    # Simulate an already-running legacy duplicate being accepted after the first timeout.
    status, _ = shop_listen.accept_job_by_ref(
        home, nick="copilot", channel="#bobiverse", repo=REPO, task="FR", ident="#5201",
    )
    assert status == "ok"
    cd._save_jobs(home, {"jobs": [{
        "repo": REPO, "task": "FR", "id": "#5201", "task_id": "legacy-task",
        "started": chair["now"],
    }]})
    timeout(chair)
    assert len(chair["posts"]) == 1
    assert len(created) == 1
    assert created[0][0] == f"stall:all-gave-up:{REPO}#5201"
    assert gitclaim.load_unaccepted(home)[0]["giveup_count"] == 2
    chair["chair"]._copilot_tick()
    assert len(created) == 1


def test_durable_giveup_survives_queue_rebuild_and_does_not_starve_next_row(chair):
    start(chair)
    timeout(chair)
    home = chair["home"]
    gitclaim._write_queue(gitclaim.queue_path(home), {
        "v": 1, "accepted": [], "done": [], "unaccepted": [
            {"repo": REPO, "task": "FR", "id": "#5201"},
            {"repo": REPO, "task": "FR", "id": "#5202"},
        ],
    })
    chair["chair"]._copilot_tick()
    assert len(chair["posts"]) == 2
    assert gitclaim.load_accepted(home)[0]["id"] == "#5202"
    assert gitclaim.load_unaccepted(home)[0]["id"] == "#5201"


def test_tracking_read_error_keeps_task_and_never_redispatches(chair):
    start(chair)
    chair["get_code"] = 503
    timeout(chair)
    timeout(chair)
    assert len(chair["posts"]) == 1
    assert gitclaim.load_accepted(chair["home"])[0]["nick"] == "copilot"
    assert cd._load_jobs(chair["home"])["jobs"]


def test_unrelated_branch_and_pr_are_not_work(chair):
    start(chair)
    chair["branches"] = [{"ref": "refs/heads/copilot/fr-52010-other"}]
    chair["pulls"] = [{
        "user": {"login": "Copilot"}, "head": {"ref": "copilot/other"},
        "body": "Closes other/repo#5201",
    }]
    timeout(chair)
    assert gitclaim.load_unaccepted(chair["home"])[0]["giveup_seats"] == "copilot"


def test_completed_webhook_does_not_resurrect_stale_task(chair):
    start(chair)
    gitclaim._write_queue(
        gitclaim.queue_path(chair["home"]),
        {"v": 1, "unaccepted": [], "accepted": [], "done": []},
    )
    timeout(chair)
    assert not gitclaim.load_unaccepted(chair["home"])
    assert not cd._load_jobs(chair["home"])["jobs"]


def test_stale_task_never_releases_an_irc_holder(chair):
    start(chair)
    home = chair["home"]
    doc = gitclaim.load_queue(home)
    doc["accepted"][0]["nick"] = "ionos-123"
    gitclaim._write_queue(gitclaim.queue_path(home), doc)
    timeout(chair)
    assert gitclaim.load_accepted(home)[0]["nick"] == "ionos-123"
    assert not gitclaim.load_unaccepted(home)
    assert not cd._load_jobs(home)["jobs"]


def test_stale_task_artifacts_do_not_count_as_live_work(chair):
    start(chair)
    chair["task"].update({
        "branch": "copilot/deleted-branch",
        "pull_request_url": f"https://github.com/{REPO}/pull/5202",
    })
    timeout(chair)
    assert gitclaim.load_unaccepted(chair["home"])[0]["giveup_seats"] == "copilot"


def test_historical_failed_session_does_not_end_running_task(chair):
    start(chair)
    chair["task"]["sessions"] = [{"state": "failed"}, {"state": "running"}]
    chair["now"] += 1
    chair["chair"]._copilot_tick()
    assert gitclaim.load_accepted(chair["home"])[0]["nick"] == "copilot"
    assert not gitclaim.load_unaccepted(chair["home"])


def test_return_checks_holder_under_queue_lock(chair):
    start(chair)
    home = chair["home"]
    doc = gitclaim.load_queue(home)
    doc["accepted"][0]["nick"] = "ionos-123"
    gitclaim._write_queue(gitclaim.queue_path(home), doc)
    status, _ = shop_listen.return_job_to_unaccepted(
        home, repo=REPO, task="FR", ident="#5201", expected_nick="copilot",
    )
    assert status == "missing"
    assert gitclaim.load_accepted(home)[0]["nick"] == "ionos-123"
