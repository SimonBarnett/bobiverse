"""FR #5201: recovery through the real ChairJobs Copilot wiring."""
from __future__ import annotations

import pytest

import chair_health
import copilot_dispatch as cd
import gitclaim
import shop_listen
import stall_filer


REPO = "SimonBarnett/bobiverse"
PR_URL = f"https://github.com/{REPO}/pull/5300"


def _row(num=5201, task="FR", **extra):
    return {
        "repo": REPO, "task": task, "id": f"#{num}", "title": "repair timeout",
        "url": f"https://github.com/{REPO}/issues/{num}", **extra,
    }


@pytest.fixture
def chair(tmp_path, monkeypatch):
    home = tmp_path / "chair"
    digest = tmp_path / "digest"
    home.mkdir()
    digest.mkdir()
    now = [1_800_000_000.0]
    monkeypatch.setattr(cd.time, "time", lambda: now[0])
    monkeypatch.setenv("BOB_DIGEST_HOME", str(digest))
    gitclaim._write_queue(
        gitclaim.queue_path(digest),
        {"v": 1, "unaccepted": [_row()], "accepted": [], "done": []},
    )
    calls = []
    responses = {
        "task": {"state": "in_progress"},
        "timeline": [], "refs": [],
        "pull": {
            "state": "open", "html_url": PR_URL,
            "user": {"login": "Copilot"}, "head": {"ref": "copilot/fr-5201-timeout"},
        },
        "ref": None,
    }

    def github(method, url, body=None):
        calls.append((method, url, body))
        if url.endswith("/copilot_internal/user"):
            return {"quota_snapshots": {"premium_interactions": {"unlimited": True}}}, 200
        if method == "POST":
            assert url.endswith("/tasks")
            return {"id": "cca-5201", "html_url": f"https://github.com/{REPO}/tasks/cca-5201"}, 201
        if "/tasks/" in url:
            return responses["task"], 200
        if "/timeline?" in url:
            value = responses["timeline"]
            return (value(url) if callable(value) else value), 200
        if "/matching-refs/" in url:
            return responses["refs"], 200
        if "/git/ref/" in url:
            return responses["ref"], 200 if responses["ref"] else 404
        if "/pulls/" in url:
            return responses["pull"], 200
        raise AssertionError(url)

    job = chair_health.ChairJobs(
        home, digest, log=lambda _: None, announce=lambda _: None,
        spawn=False, token_loader=lambda: ("test-only", "test"),
        clock=lambda: now[0],
    )
    monkeypatch.setattr(job, "_github_json", github)
    job._copilot_tick()
    assert len([c for c in calls if c[0] == "POST"]) == 1
    return job, digest, now, responses, calls


def _advance(chair, seconds=cd.TASK_TIMEOUT_S + 1):
    job, _, now, _, _ = chair
    now[0] += seconds
    job._copilot_tick()


def _no_redispatch(chair):
    assert len([c for c in chair[4] if c[0] == "POST"]) == 1


@pytest.mark.parametrize("work", ["branch", "issue-pr", "task-pr", "task-branch", "session-branch"])
def test_timeout_tracks_existing_work(chair, work):
    _, digest, _, responses, _ = chair
    if work == "branch":
        responses["refs"] = [{"ref": "refs/heads/copilot/fr-5201-timeout"}]
    elif work == "issue-pr":
        responses["timeline"] = [{
            "event": "cross-referenced",
            "source": {"issue": {
                "number": 5300, "state": "open", "pull_request": {"html_url": PR_URL},
            }},
        }]
    elif work == "task-pr":
        responses["task"]["pull_request_url"] = PR_URL
    else:
        responses["ref"] = {"object": {"sha": "abc123"}}
        if work == "task-branch":
            responses["task"]["branch_name"] = "copilot/fr-5201-timeout"
        else:
            responses["task"]["sessions"] = [{"branch": "copilot/fr-5201-timeout"}]
    _advance(chair)
    _advance(chair, cd.CACHE_S + 1)
    _no_redispatch(chair)
    queue = gitclaim.load_queue(digest)
    assert queue["accepted"][0]["nick"] == "copilot"
    assert queue["unaccepted"] == []
    tracked = cd._load_jobs(digest)["jobs"][0]
    assert tracked.get("branch") or tracked.get("pull_request")
    assert tracked["task_id"] == "cca-5201"
    assert not gitclaim.ledger_blocks(gitclaim.ledger_load(digest), _row(), "copilot")


@pytest.mark.parametrize("state", ["in_progress", "failed", "cancelled", "canceled"])
def test_no_work_gives_up_durably_and_offers_irc(chair, state):
    _, digest, _, responses, _ = chair
    responses["task"]["state"] = state
    _advance(chair, cd.TASK_TIMEOUT_S + 1 if state == "in_progress" else cd.CACHE_S + 1)
    queue = gitclaim.load_queue(digest)
    row = queue["unaccepted"][0]
    assert queue["accepted"] == []
    assert row["giveup_seats"] == "copilot"
    assert row["giveup_count"] == 1
    assert row["cooldown_until"]
    assert gitclaim.row_gave_up_by(row, "copilot")
    assert not gitclaim.row_on_cooldown(row, cd.time.time(), nick="ionos-123")
    assert gitclaim.ledger_blocks(gitclaim.ledger_load(digest), row, "copilot")
    assert cd._load_jobs(digest)["jobs"] == []
    _advance(chair, cd.TASK_TIMEOUT_S + 1)
    _no_redispatch(chair)
    status, offered = gitclaim.offer_focus_top(
        digest, "ionos-123", "#ionos", now=cd.time.time(), offered_via="bored",
    )
    assert status == "ok"
    assert offered["id"] == "#5201"
    assert offered["offered_to"] == "ionos-123"


def test_queue_rebuild_cannot_erase_copilot_giveup(chair):
    job, digest, _, _, _ = chair
    _advance(chair)
    gitclaim._write_queue(
        gitclaim.queue_path(digest),
        {"v": 1, "unaccepted": [_row(), _row(5202)], "accepted": [], "done": []},
    )
    assert cd.dispatch_row(digest, _row(), post=lambda *_: pytest.fail("redispatch"))["status"] == "skip"
    job._copilot_tick()
    posts = [c for c in chair[4] if c[0] == "POST"]
    assert len(posts) == 2
    assert "5202" in posts[-1][2]["prompt"]


def test_repeated_legacy_timeout_files_existing_stall(chair, monkeypatch):
    _, digest, _, _, _ = chair
    findings = []
    monkeypatch.setattr(stall_filer, "apply_findings", lambda rows, **kw: findings.extend(rows))
    _advance(chair)
    # A legacy duplicate task (or explicit operator assignment) times out again.
    status, _ = shop_listen.accept_job_by_ref(
        digest, nick="copilot", channel="#bobiverse", repo=REPO, task="FR", ident="#5201",
    )
    assert status == "ok"
    cd._save_jobs(digest, {"jobs": [{
        "repo": REPO, "task": "FR", "id": "#5201",
        "task_id": "legacy-duplicate", "started": cd.time.time(),
    }]})
    _advance(chair)
    _no_redispatch(chair)
    assert len(findings) == 1
    assert findings[0]["fingerprint"] == f"stall:all-gave-up:{REPO}#5201"
    assert gitclaim.load_unaccepted(digest)[0]["giveup_count"] == 2


def test_repeated_work_timeout_stalls_without_abandoning_branch(chair, monkeypatch):
    _, digest, _, responses, _ = chair
    findings = []
    monkeypatch.setattr(stall_filer, "apply_findings", lambda rows, **kw: findings.extend(rows))
    responses["refs"] = [{"ref": "refs/heads/copilot/fr-5201-timeout"}]
    _advance(chair)
    assert not findings
    _advance(chair)
    _no_redispatch(chair)
    assert len(findings) == 1
    assert gitclaim.load_queue(digest)["accepted"]


def test_recovery_api_failure_does_not_duplicate_work(chair):
    _, digest, _, responses, _ = chair
    responses["timeline"] = {"message": "API unavailable"}
    _advance(chair)
    _advance(chair, cd.CACHE_S + 1)
    _no_redispatch(chair)
    assert gitclaim.load_queue(digest)["accepted"]


def test_finished_tracker_does_not_resurrect_row(chair):
    _, digest, _, _, _ = chair
    shop_listen.complete_job_by_ref(
        digest, nick="copilot", repo=REPO, task="FR", ident="#5201", url=PR_URL,
    )
    _advance(chair)
    _no_redispatch(chair)
    assert not any(row["id"] == "#5201" for row in gitclaim.load_unaccepted(digest))
    assert cd._load_jobs(digest)["jobs"] == []


def test_job_update_preserves_other_tasks(tmp_path):
    first = {"repo": REPO, "task": "FR", "id": "#1", "task_id": "first"}
    second = {"repo": REPO, "task": "FR", "id": "#2", "task_id": "second"}
    cd._save_jobs(tmp_path, {"jobs": [first, second]})
    cd._update_job(tmp_path, dict(first, checked_at=123))
    assert cd._load_jobs(tmp_path)["jobs"][1] == second
    cd._update_job(tmp_path, first, remove=True)
    assert cd._load_jobs(tmp_path)["jobs"] == [second]


def test_row_dispatch_gates_giveup_and_human():
    for fields in (
        {"copilot_gave_up": True}, {"giveup_seats": "COPILOT"}, {"needs_human": True},
    ):
        assert not cd.should_dispatch(_row(**fields), allowance=True)
