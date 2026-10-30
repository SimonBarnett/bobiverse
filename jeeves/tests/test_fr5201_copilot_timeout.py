"""FR #5201: real chair ticks must not turn a timeout into another CCA task."""
from __future__ import annotations

import pytest

import bobreport
import chair_health
import copilot_dispatch as cd
import gitclaim
import registered_machines
import shop_listen
import stall_filer


REPO = "SimonBarnett/bobiverse"
IDENT = "#5201"


def _chair(tmp_path, monkeypatch, *, state="running", work="", task_extra=None, task="FR"):
    home = tmp_path / "chair"
    digest = tmp_path / "digest"
    home.mkdir()
    digest.mkdir()
    monkeypatch.setenv("BOB_DIGEST_HOME", str(digest))
    clock = [1_000_000.0]
    monkeypatch.setattr(cd.time, "time", lambda: clock[0])
    row = {
        "repo": REPO, "task": task, "id": IDENT,
        "url": f"https://github.com/{REPO}/{'pull' if task == 'MRB' else 'issues'}/5201",
        "title": "Fix timeout loop",
    }
    gitclaim._write_queue(
        gitclaim.queue_path(digest),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    calls = []
    logs = []
    j = chair_health.ChairJobs(
        home, digest, log=logs.append, spawn=False,
        token_loader=lambda: ("FAKE_TOKEN", "test"),
        clock=lambda: clock[0], announce=logs.append,
    )
    settings = {"state": "running", "work": work, "error": False}

    def github(method, url, body=None):
        calls.append((method, url, body))
        if "copilot_internal/user" in url:
            return {"quota_snapshots": {"premium_interactions": {"unlimited": True}}}, 200
        if method == "POST":
            assert url.endswith("/tasks")
            return {"id": "task-1", "html_url": f"https://github.com/{REPO}/tasks/task-1"}, 201
        if settings["error"]:
            return {"message": "unavailable"}, 503
        if "/tasks/task-1" in url:
            return {"state": settings["state"], **(task_extra or {})}, 200
        if "/pulls?" in url:
            if settings["work"] == "pr":
                return [{
                    "number": 5300, "state": "open", "draft": True,
                    "html_url": f"https://github.com/{REPO}/pull/5300",
                    "body": f"Closes {REPO}{IDENT}",
                    "user": {"login": "Copilot"},
                    "head": {"ref": "copilot/fix-timeout-loop"},
                }], 200
            return [], 200
        if "/git/ref/heads/" in url:
            return {"object": {"sha": "abc123"}}, 200
        if "/git/matching-refs/heads/" in url:
            if settings["work"] in ("branch", "wrong-branch"):
                name = "copilot/fr-5201-fix" if settings["work"] == "branch" else "copilot/fr-52010-fix"
                return [{"ref": f"refs/heads/{name}", "object": {"sha": "abc123"}}], 200
            return [], 200
        raise AssertionError(f"unexpected API call: {method} {url}")

    monkeypatch.setattr(j, "_github_json", github)
    j._copilot_tick()
    assert len(_posts(calls)) == 1
    settings["state"] = state
    clock[0] += cd.TASK_TIMEOUT_S + 1
    return j, digest, clock, settings, calls, logs


def _posts(calls):
    return [c for c in calls if c[0] == "POST"]


@pytest.mark.parametrize("work", ["pr", "branch"])
@pytest.mark.parametrize("state", ["running", "failed", "cancelled"])
def test_timeout_tracks_existing_work(tmp_path, monkeypatch, work, state):
    j, home, clock, settings, calls, logs = _chair(
        tmp_path, monkeypatch, work=work, state=state
    )
    j._copilot_tick()
    j._copilot_tick()
    assert len(_posts(calls)) == 1
    assert gitclaim.load_accepted(home)[0]["nick"] == "copilot"
    tracked = cd._load_jobs(home)["jobs"][0]
    assert tracked["task_id"] == "task-1"
    assert tracked.get("branch")
    assert tracked["check_after"] > clock[0]
    assert "copilot timeout" not in "\n".join(logs)


@pytest.mark.parametrize("state", ["running", "failed", "cancelled", "canceled"])
def test_no_work_gives_up_durably_and_leaves_job_for_irc(tmp_path, monkeypatch, state):
    j, home, clock, settings, calls, logs = _chair(tmp_path, monkeypatch, state=state)
    j._copilot_tick()
    row = gitclaim.load_unaccepted(home)[0]
    assert row["giveup_count"] == 1
    assert row["giveup_seats"] == "copilot"
    assert row.get("cooldown_until")
    assert gitclaim.row_on_cooldown(row, clock[0], "copilot")
    assert not gitclaim.row_on_cooldown(row, clock[0], "worker-123")
    assert not gitclaim.row_gave_up_by(row, "worker-123")
    assert not gitclaim.ledger_blocks(gitclaim.ledger_load(home), row, "worker-123")
    assert gitclaim.ledger_blocks(gitclaim.ledger_load(home), row, "copilot")
    assert not cd.should_dispatch(row, allowance=True)
    assert not gitclaim.load_accepted(home)
    assert not cd._load_jobs(home)["jobs"]
    registered_machines.save_registered(home, {"worker"})
    digest = bobreport.empty_digest()
    digest["machines"]["worker"] = bobreport._empty_machine("worker")
    digest["machines"]["worker"]["worker_list"] = [{"nick": "worker-123", "state": "idle"}]
    bobreport.save_digest(home, digest)
    st, offered = gitclaim.offer_focus_top(
        home, "worker-123", "#worker", now=clock[0],
        issue_open=lambda *args: True, is_pull=lambda *args: False,
    )
    assert st == "ok" and offered["id"] == IDENT
    j._copilot_tick()
    # Resync can drop row stamps: the durable ledger must still block dispatch.
    rebuilt = {k: v for k, v in row.items() if not k.startswith("giveup") and k != "cooldown_until"}
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [rebuilt], "accepted": [], "done": []},
    )
    clock[0] += cd.TASK_TIMEOUT_S * 2
    j._copilot_tick()
    assert cd.dispatch_row(home, rebuilt, post=lambda *args: pytest.fail("redispatched"))["status"] == "skip"
    assert len(_posts(calls)) == 1
    assert any("copilot" in line and "DONE" in line for line in logs)
    st, accepted = shop_listen.accept_job_by_ref(
        home, nick="worker-123", channel="#worker",
        repo=REPO, task="FR", ident=IDENT,
    )
    assert st == "ok" and accepted["nick"] == "worker-123"


def test_failed_task_requeues_before_timeout(tmp_path, monkeypatch):
    j, home, clock, settings, calls, logs = _chair(tmp_path, monkeypatch, state="failed")
    clock[0] -= cd.TASK_TIMEOUT_S
    j._copilot_tick()
    assert gitclaim.load_unaccepted(home)[0]["giveup_count"] == 1
    assert len(_posts(calls)) == 1


def test_repeated_timeout_files_stall_and_keeps_existing_branch(tmp_path, monkeypatch):
    j, home, clock, settings, calls, logs = _chair(tmp_path, monkeypatch, work="branch")
    filed = []
    monkeypatch.setattr(stall_filer, "default_create", lambda title, body: filed.append((title, body)) or {"number": 5400})
    j._copilot_tick()
    clock[0] += cd.TASK_TIMEOUT_S + 1
    j._copilot_tick()
    j._copilot_tick()
    assert len(_posts(calls)) == 1
    assert len(filed) == 1
    assert f"stall:all-gave-up:{REPO}{IDENT}" in filed[0][1]
    assert cd._load_jobs(home)["jobs"][0]["task_id"] == "task-1"


def test_legacy_second_timeout_files_stall_without_redispatch(tmp_path, monkeypatch):
    j, home, clock, settings, calls, logs = _chair(tmp_path, monkeypatch)
    gitclaim.ledger_note_event(home, "copilot", "GIVEUP", "FR", REPO, IDENT)
    filed = []
    monkeypatch.setattr(stall_filer, "default_create", lambda title, body: filed.append(body) or {"number": 5400})
    j._copilot_tick()
    j._copilot_tick()
    assert len(_posts(calls)) == 1
    assert len(filed) == 1
    assert gitclaim.load_unaccepted(home)[0]["giveup_seats"] == "copilot"


def test_work_check_error_keeps_tracking(tmp_path, monkeypatch):
    j, home, clock, settings, calls, logs = _chair(tmp_path, monkeypatch)
    settings["error"] = True
    j._copilot_tick()
    assert gitclaim.load_accepted(home)
    assert cd._load_jobs(home)["jobs"]
    assert len(_posts(calls)) == 1
    assert not gitclaim.ledger_blocks(gitclaim.ledger_load(home), gitclaim.load_accepted(home)[0], "copilot")


def test_task_reported_branch_is_checked(tmp_path, monkeypatch):
    j, home, clock, settings, calls, logs = _chair(
        tmp_path, monkeypatch, task_extra={"branch": "copilot/fix-timeout"}
    )
    j._copilot_tick()
    assert cd._load_jobs(home)["jobs"][0]["branch"] == "copilot/fix-timeout"
    assert any("/git/ref/heads/copilot%2Ffix-timeout" in c[1] for c in calls)
    assert len(_posts(calls)) == 1


def test_other_issue_branch_does_not_hold_job(tmp_path, monkeypatch):
    j, home, clock, settings, calls, logs = _chair(tmp_path, monkeypatch, work="wrong-branch")
    j._copilot_tick()
    assert not gitclaim.load_accepted(home)
    assert gitclaim.load_unaccepted(home)[0]["giveup_count"] == 1


def test_pr_webhook_completion_does_not_resurrect_stale_task(tmp_path, monkeypatch):
    j, home, clock, settings, calls, logs = _chair(tmp_path, monkeypatch)
    payload = {
        "action": "opened", "repository": {"full_name": REPO},
        "pull_request": {
            "number": 5300, "title": "Fix timeout", "body": f"Closes {REPO}{IDENT}",
            "state": "open", "draft": False, "merged": False,
            "html_url": f"https://github.com/{REPO}/pull/5300",
            "user": {"login": "Copilot"}, "labels": [],
        },
    }
    assert bobreport.apply_git_webhook(home, "pull_request", payload).ok
    # Isolate the superseded FR from the independently queued MRB.
    monkeypatch.setattr(cd, "has_allowance", lambda home: False)
    j._copilot_tick()
    assert not cd._load_jobs(home)["jobs"]
    assert not any(r.get("id") == IDENT for r in gitclaim.load_unaccepted(home))
    assert len(_posts(calls)) == 1


def test_durable_blocked_row_does_not_starve_next_job(tmp_path, monkeypatch):
    j, home, clock, settings, calls, logs = _chair(tmp_path, monkeypatch)
    j._copilot_tick()
    row = gitclaim.load_unaccepted(home)[0]
    clean = {k: row[k] for k in ("repo", "task", "id", "url", "title")}
    next_row = dict(clean, id="#5202", url=f"https://github.com/{REPO}/issues/5202")
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [clean, next_row], "accepted": [], "done": []},
    )
    j._copilot_tick()
    assert len(_posts(calls)) == 2
    assert gitclaim.load_accepted(home)[0]["id"] == "#5202"


def test_active_tracking_survives_queue_rebuild(tmp_path, monkeypatch):
    j, home, clock, settings, calls, logs = _chair(tmp_path, monkeypatch, work="branch")
    row = gitclaim.load_accepted(home)[0]
    row.pop("nick", None)
    row.pop("accepted_ts", None)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    j._copilot_tick()
    j._copilot_tick()
    assert len(_posts(calls)) == 1
    assert gitclaim.load_accepted(home)[0]["nick"] == "copilot"
    assert cd._load_jobs(home)["jobs"][0]["task_id"] == "task-1"


def test_timeout_must_not_release_another_seats_job(tmp_path, monkeypatch):
    j, home, clock, settings, calls, logs = _chair(tmp_path, monkeypatch)
    original = j._github_json

    def github(method, url, body=None):
        response = original(method, url, body)
        if "/pulls?" in url:
            doc = gitclaim.load_queue(home)
            doc["accepted"][0]["nick"] = "worker-123"
            gitclaim._write_queue(gitclaim.queue_path(home), doc)
        return response

    monkeypatch.setattr(j, "_github_json", github)
    j._copilot_tick()
    assert gitclaim.load_accepted(home)[0]["nick"] == "worker-123"
    assert not gitclaim.load_unaccepted(home)
    assert len(_posts(calls)) == 1


def test_pr_search_paginates_before_giving_up(tmp_path, monkeypatch):
    j, home, clock, settings, calls, logs = _chair(tmp_path, monkeypatch, work="pr")
    original = j._github_json
    pages = []

    def github(method, url, body=None):
        if "/pulls?" in url:
            pages.append(url)
            if "&page=1" in url:
                return [{"body": "unrelated", "head": {"ref": "feature"}}] * 100, 200
        return original(method, url, body)

    monkeypatch.setattr(j, "_github_json", github)
    j._copilot_tick()
    assert len(pages) == 2
    assert cd._load_jobs(home)["jobs"][0]["pr_url"].endswith("/pull/5300")
    assert len(_posts(calls)) == 1


def test_stall_reports_do_not_spawn_another_stall(tmp_path, monkeypatch):
    j, home, clock, settings, calls, logs = _chair(tmp_path, monkeypatch)
    doc = gitclaim.load_queue(home)
    doc["accepted"][0]["body"] = "<!-- stall-fp:stall:all-gave-up:example -->"
    gitclaim._write_queue(gitclaim.queue_path(home), doc)
    gitclaim.ledger_note_event(home, "copilot", "GIVEUP", "FR", REPO, IDENT)
    monkeypatch.setattr(
        stall_filer, "default_create", lambda *args: pytest.fail("recursive stall")
    )
    j._copilot_tick()
    assert gitclaim.load_unaccepted(home)[0]["giveup_seats"] == "copilot"
    assert not (j.home / stall_filer.STATE_NAME).exists()


def test_chair_and_copilot_stalls_share_dedupe_state(tmp_path, monkeypatch):
    j, home, clock, settings, calls, logs = _chair(tmp_path, monkeypatch, work="branch")
    filed = []
    monkeypatch.setattr(stall_filer, "default_create", lambda title, body: filed.append(body) or {"number": 5400})
    j._copilot_tick()
    clock[0] += cd.TASK_TIMEOUT_S + 1
    j._copilot_tick()
    assert len(filed) == 1
    assert (j.home / stall_filer.STATE_NAME).is_file()
    assert not (home / stall_filer.STATE_NAME).exists()


def test_dispatch_cooldown_uses_injected_time(tmp_path, monkeypatch):
    cd.set_allowance(tmp_path, remaining=5)
    row = {
        "repo": REPO, "task": "FR", "id": IDENT,
        "cooldown_until": "2000-01-01T00:00:00Z",
    }
    assert not cd.should_dispatch(row, allowance=True, now=1.0)
    assert cd.dispatch_row(
        tmp_path, row, now=1.0, post=lambda *args: pytest.fail("cooldown ignored")
    )["status"] == "skip"


@pytest.mark.parametrize("task", ["FIX", "MRB"])
def test_fix_and_mrb_failures_use_same_durable_giveup(tmp_path, monkeypatch, task):
    j, home, clock, settings, calls, logs = _chair(
        tmp_path, monkeypatch, state="failed", task=task
    )
    j._copilot_tick()
    j._copilot_tick()
    row = gitclaim.load_unaccepted(home)[0]
    assert row["giveup_count"] == 1
    assert gitclaim.ledger_blocks(gitclaim.ledger_load(home), row, "copilot")
    assert len(_posts(calls)) == 1


def test_missing_task_still_checks_for_work(tmp_path, monkeypatch):
    j, home, clock, settings, calls, logs = _chair(tmp_path, monkeypatch, work="branch")
    original = j._github_json

    def github(method, url, body=None):
        if "/tasks/task-1" in url:
            return {"message": "not found"}, 404
        return original(method, url, body)

    monkeypatch.setattr(j, "_github_json", github)
    j._copilot_tick()
    assert cd._load_jobs(home)["jobs"][0]["branch"] == "copilot/fr-5201-fix"
    assert len(_posts(calls)) == 1
