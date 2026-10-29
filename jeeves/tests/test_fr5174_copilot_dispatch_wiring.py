"""FR #5174: Copilot dispatch must not mark jobs taken without a real task.

Defects from hotpatch of #5173:
1. Pool read must use a wired fetch (not raise forever).
2. Unknown pool → no dispatch (fail closed); unlimited+remaining 0 still OK.
3. No POST / send failure → job stays unaccepted; no hand-off announce.
4. Machine-pinned rows (require_machine) skipped for Copilot.
5. Webhook ensure logs ok/created/repaired/error per repo.
6. Live ChairJobs.tick passes fetch_user + post into copilot_dispatch.tick.
"""
from __future__ import annotations

import json
from pathlib import Path
import urllib.error

import bobreport
import chair_health as ch
import copilot_dispatch as cd
import gitclaim
import pytest


REPO = "SimonBarnett/a-search"
UNLIMITED = {
    "copilot_plan": "business",
    "quota_reset_date_utc": "2026-11-01T00:00:00.000Z",
    "quota_snapshots": {
        "premium_interactions": {
            "credits_used": 39,
            "entitlement": 0,
            "remaining": 0,
            "percent_remaining": 100.0,
            "unlimited": True,
            "overage_permitted": True,
        }
    },
}


def _row(task="FR", num=5058, **extra):
    row = {
        "repo": REPO,
        "task": task,
        "id": f"#{num}",
        "url": f"https://github.com/{REPO}/issues/{num}",
        "title": "do the thing",
        "ts": "t",
        "event": "issues",
        "action": "opened",
        "line": f"{task} {REPO}#{num}",
    }
    row.update(extra)
    return row


def _queue(home: Path, rows: list) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": rows, "accepted": [], "done": []},
    )


def test_unknown_pool_no_dispatch(tmp_path):
    """Unknown / failed pool read must fail closed (no steal of IRC jobs)."""
    cd.refresh_allowance(tmp_path, fetch_user=lambda: (_ for _ in ()).throw(RuntimeError("no token")), now=1.0)
    assert cd.load_allowance(tmp_path).get("state") == "unknown"
    assert cd.has_allowance(tmp_path) is False
    assert cd.allowance_from_pool({"state": "unknown"}) is False
    assert cd.allowance_from_pool({"state": "unknown", "unlimited": True}) is False
    # Unlimited business plan with remaining 0 still available
    cd.refresh_allowance(tmp_path, fetch_user=lambda: UNLIMITED, now=400.0)
    assert cd.has_allowance(tmp_path) is True
    assert cd.allowance_from_pool(cd.parse_user_quota(UNLIMITED)) is True


def test_send_failure_leaves_job_and_no_handoff(tmp_path):
    cd.refresh_allowance(tmp_path, fetch_user=lambda: UNLIMITED, now=1.0)
    _queue(tmp_path, [_row(num=5058)])
    announced: list[str] = []

    def bad_post(_path, _body):
        return {"status": 500, "message": "boom"}

    out = cd.dispatch_row(
        tmp_path,
        _row(num=5058),
        post=bad_post,
        announce=announced.append,
    )
    assert out.get("status") != "dispatched"
    assert any(r.get("id") == "#5058" for r in gitclaim.load_unaccepted(tmp_path))
    assert not any(
        str(r.get("nick") or "").lower() == "copilot"
        for r in (gitclaim.load_queue(tmp_path).get("accepted") or [])
    )
    assert announced == []

    # post=None must also refuse to stamp
    out2 = cd.dispatch_row(
        tmp_path, _row(num=5058), post=None, announce=announced.append
    )
    assert out2.get("status") in ("error", "no-post", "send-failed")
    assert announced == []


def test_pinned_job_skipped(tmp_path):
    cd.refresh_allowance(tmp_path, fetch_user=lambda: UNLIMITED, now=1.0)
    pinned = _row(num=5221, require_machine="redqueen")
    assert cd.should_dispatch(pinned, allowance=True) is False
    _queue(tmp_path, [pinned])
    posts: list = []

    def post(path, body):
        posts.append((path, body))
        return {"status": 201, "id": "task-1", "html_url": "https://example/tasks/1"}

    out = cd.tick(tmp_path, post=post, fetch_user=lambda: UNLIMITED, now=2.0)
    assert out.get("dispatched") == 0
    assert posts == []
    assert any(r.get("id") == "#5221" for r in gitclaim.load_unaccepted(tmp_path))


def test_webhook_ensure_logs_action_per_repo(tmp_path, monkeypatch):
    logs: list[str] = []
    # Write an explicit served-repo list so the chair does not expand fleet defaults.
    (tmp_path / "resync-repos.txt").write_text(
        "SimonBarnett/bobiverse\nSimonBarnett/a-search\n", encoding="utf-8"
    )
    monkeypatch.delenv("JEEVES_RESYNC_REPOS", raising=False)
    j = ch.ChairJobs(
        tmp_path,
        tmp_path,
        log=logs.append,
        spawn=False,
        token_loader=lambda: ("tok", "test"),
        fetch_json=None,
        clock=lambda: 1_000_000.0,
    )
    actions = {"SimonBarnett/bobiverse": "ok", "SimonBarnett/a-search": "create"}

    def fake_ensure(repo, **kw):
        return {"action": actions.get(repo, "ok"), "repo": repo}

    import copilot_dispatch as mod

    monkeypatch.setattr(mod, "ensure_repo_webhook", fake_ensure)
    j._ensure_webhooks()
    joined = "\n".join(logs)
    assert "webhook-ensure repo=SimonBarnett/bobiverse action=ok" in joined
    assert "webhook-ensure repo=SimonBarnett/a-search action=create" in joined
    bare_done = [
        ln
        for ln in logs
        if "webhook-ensure repo=" in ln and "action=" not in ln and ln.strip().endswith("done")
    ]
    assert bare_done == [], bare_done



def test_chair_tick_passes_fetch_and_post(tmp_path, monkeypatch):
    """End-to-end: live ChairJobs wiring supplies fetch_user + post into tick().

    Queue lives under digest_home (may differ from chair home).
    """
    chair_home = tmp_path / "jeeves"
    digest_home = tmp_path / "digest"
    chair_home.mkdir()
    digest_home.mkdir()
    seen: dict = {}
    _queue(digest_home, [_row(num=5139)])

    def fake_tick(home, **kw):
        seen["home"] = Path(home)
        seen["fetch_user"] = kw.get("fetch_user")
        seen["post"] = kw.get("post")
        seen["announce"] = kw.get("announce")
        assert callable(seen["fetch_user"])
        assert callable(seen["post"])
        user = seen["fetch_user"]()
        assert isinstance(user, dict) and user.get("copilot_plan") == "business"
        resp = seen["post"](
            "agents/repos/SimonBarnett/a-search/tasks", {"prompt": "x"}
        )
        assert resp.get("id") == "t1" or int(resp.get("status") or 0) in (200, 201, 202)
        return {"dispatched": 1, "timed_out": 0}

    monkeypatch.setattr(cd, "tick", fake_tick)
    logs: list[str] = []

    def fake_gh(method, url, body=None):
        if "copilot_internal/user" in url:
            return UNLIMITED, 200
        if "/tasks" in str(url) and str(method).upper() == "POST":
            return {"id": "t1", "html_url": "https://example/t1"}, 201
        return {}, 200

    j = ch.ChairJobs(
        chair_home,
        digest_home,
        log=logs.append,
        spawn=False,
        token_loader=lambda: ("fake-token", "test"),
        fetch_json=None,
        clock=lambda: 1_000_000.0,
        announce=lambda s: logs.append(f"ANN {s}"),
    )
    monkeypatch.setattr(j, "_github_json", fake_gh)
    j._copilot_tick()
    assert seen.get("home") == digest_home.resolve() or seen.get("home") == digest_home
    assert seen.get("fetch_user") is not None
    assert seen.get("post") is not None
    assert seen.get("announce") is j.announce
    assert any("dispatched=1" in ln for ln in logs)


def test_successful_post_then_dispatch(tmp_path):
    cd.refresh_allowance(tmp_path, fetch_user=lambda: UNLIMITED, now=1.0)
    _queue(tmp_path, [_row(num=16)])
    announced: list[str] = []

    def ok_post(path, body):
        assert "prompt" in body and "problem_statement" not in body
        assert path.endswith("/tasks")
        return {"status": 201, "id": "abc", "html_url": "https://github.com/tasks/abc"}

    out = cd.dispatch_row(
        tmp_path, _row(num=16), post=ok_post, announce=announced.append, now=2.0
    )
    assert out.get("status") == "dispatched"
    assert announced and "copilot:" in announced[0].lower()
    assert any(
        str(r.get("nick") or "").lower() == "copilot" and r.get("id") == "#16"
        for r in (gitclaim.load_queue(tmp_path).get("accepted") or [])
    )


class _Response:
    def __init__(self, data, status=200):
        self.data = data
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.data).encode("utf-8")


def _live_chair(tmp_path, monkeypatch, rows):
    chair_home = tmp_path / "chair"
    digest_home = tmp_path / "digest"
    chair_home.mkdir()
    digest_home.mkdir()
    monkeypatch.setenv("JEEVES_RESYNC_REPOS", REPO)
    monkeypatch.setattr(ch.gab, "webhook_gap_due", lambda *_a, **_kw: False)
    logs, announced = [], []
    chair = ch.ChairJobs(
        chair_home, digest_home, log=logs.append, announce=announced.append,
        spawn=False, token_loader=lambda: ("test-token", "test"),
        clock=lambda: 1_000_000.0,
    )
    _queue(digest_home, rows)
    chair.next_copilot = 0
    return chair, digest_home, logs, announced


@pytest.mark.parametrize(
    "pool, pool_status, task_response, task_status, raises, pin, repo, dispatched, sends",
    [
        (UNLIMITED, 200, {"id": "task-1"}, 201, False, {}, REPO, True, True),
        ({}, 200, {"id": "task-1"}, 201, False, {}, REPO, False, False),
        (None, 200, {"id": "task-1"}, 201, False, {}, REPO, False, False),
        (UNLIMITED, 503, {"id": "task-1"}, 201, False, {}, REPO, False, False),
        (UNLIMITED, 200, {}, 202, False, {}, REPO, False, True),
        (UNLIMITED, 200, {"id": "not-a-task"}, 500, False, {}, REPO, False, True),
        (UNLIMITED, 200, {"id": "not-a-task", "status": 201}, 500, False, {}, REPO, False, True),
        (UNLIMITED, 200, {"id": "not-a-task"}, 302, False, {}, REPO, False, True),
        (UNLIMITED, 200, {}, 201, True, {}, REPO, False, True),
        (UNLIMITED, 200, {"id": "task-1"}, 201, False,
         {"require_machine": "redqueen"}, REPO, False, False),
        (UNLIMITED, 200, {"id": "task-1"}, 201, False,
         {"require_machine": "redqueen"}, "SimonBarnett/bobiverse", False, False),
        (UNLIMITED, 200, {"id": "task-1"}, 201, False,
         {"body": "require_machine=redqueen"}, REPO, False, False),
    ],
)
def test_live_chair_dispatch(
    tmp_path, monkeypatch, pool, pool_status, task_response, task_status,
    raises, pin, repo, dispatched, sends,
):
    row = _row(num=5139, **pin)
    row["repo"] = repo
    chair, home, logs, announced = _live_chair(tmp_path, monkeypatch, [row])
    before = gitclaim.queue_path(home).read_bytes()
    requests = []
    real_tick = cd.tick
    wiring = []

    def tick(home, **kwargs):
        wiring.append(kwargs)
        assert callable(kwargs["fetch_user"]) and callable(kwargs["post"])
        return real_tick(home, **kwargs)

    def urlopen(req, **_kwargs):
        requests.append(req)
        assert req.get_header("Authorization") == "Bearer " + "test-token"
        if req.get_method() == "GET":
            assert req.full_url == "https://api.github.com/copilot_internal/user"
            if pool is None:
                raise urllib.error.URLError("offline")
            return _Response(pool, pool_status)
        assert req.get_method() == "POST"
        assert req.full_url == f"https://api.github.com/agents/repos/{repo}/tasks"
        assert "prompt" in json.loads(req.data)
        assert not gitclaim.load_accepted(home)
        assert announced == []
        if raises:
            raise urllib.error.URLError("offline")
        return _Response(task_response, task_status)

    monkeypatch.setattr(cd, "tick", tick)
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    assert chair.tick() is True
    assert wiring and wiring[0]["announce"] is chair.announce
    assert len(requests) == 1 + int(sends)
    assert bool(gitclaim.load_accepted(home)) is dispatched
    assert bool(announced) is dispatched
    if dispatched:
        assert cd._load_jobs(home)["jobs"][0]["task_id"] == "task-1"
        assert any("dispatched=1" in line for line in logs)
    else:
        assert gitclaim.queue_path(home).read_bytes() == before
        assert not cd._load_jobs(home)["jobs"]
        assert announced == []


@pytest.mark.parametrize("failure_method", ["GET", "POST", "PATCH", None])
def test_live_chair_webhook_results(tmp_path, monkeypatch, failure_method):
    chair, _home, logs, _announced = _live_chair(tmp_path, monkeypatch, [])
    repos = [f"SimonBarnett/{name}" for name in ("missing", "repair", "ok")]
    monkeypatch.setenv("JEEVES_RESYNC_REPOS", ",".join(repos))
    stalls = []
    monkeypatch.setattr(cd, "file_webhook_stall", lambda _home, **kw: stalls.append(kw))
    chair.next_copilot = float("inf")
    chair.next_webhook_ensure = 0

    def urlopen(req, **_kwargs):
        assert req.get_header("Authorization") == "Bearer " + "test-token"
        if req.get_method() == failure_method:
            raise urllib.error.URLError("offline")
        if req.get_method() == "GET":
            if "/missing/" in req.full_url:
                return _Response([])
            events = ["push"] if "/repair/" in req.full_url else list(cd.REQUIRED_HOOK_EVENTS)
            return _Response([{
                "id": 1, "active": True, "events": events,
                "config": {"url": cd.GIT_HOOK_URL},
            }])
        return _Response({"id": 1}, 201)

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    assert chair.tick() is True
    expected = ["create", "repair", "ok"]
    for repo, method, action in zip(repos, ["POST", "PATCH", None], expected):
        if failure_method == "GET" or (failure_method and failure_method == method):
            action = "error"
            assert any(stall["repo"] == repo for stall in stalls)
        assert any(f"webhook-ensure repo={repo} action={action}" in line for line in logs)
