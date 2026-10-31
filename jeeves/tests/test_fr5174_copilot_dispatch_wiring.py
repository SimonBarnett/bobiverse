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

import bobreport
import chair_health as ch
import copilot_dispatch as cd
import focus_ignore
import gitclaim


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


def _row(task="FR", num=5058, repo=REPO, **extra):
    row = {
        "repo": repo,
        "task": task,
        "id": f"#{num}",
        "url": f"https://github.com/{repo}/issues/{num}",
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
    # Unlimited business plan with remaining 0 still available
    cd.refresh_allowance(tmp_path, fetch_user=lambda: UNLIMITED, now=400.0)
    assert cd.has_allowance(tmp_path) is True
    assert cd.allowance_from_pool(cd.parse_user_quota(UNLIMITED)) is True


def test_send_failure_leaves_job_and_no_handoff(tmp_path):
    _focus_high(tmp_path)
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
    _focus_high(tmp_path)
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
    _focus_high(tmp_path)
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


def _focus_high(home):
    doc = focus_ignore.empty_focus()
    doc["repos"] = {
        repo: {"priority": 1, "label": "high"} for repo in (
            "SimonBarnett/bobiverse",
            "SimonBarnett/a-search",
        )
    }
    focus_ignore.save_focus(home, doc)


def test_real_chair_dispatches_only_high_priority_offerable_jobs(tmp_path, monkeypatch):
    chair_home = tmp_path / "jeeves"
    digest_home = tmp_path / "digest"
    chair_home.mkdir()
    digest_home.mkdir()
    # FR #5267: dispatch stays off until copilot-allowance.json exists.
    (digest_home / "copilot-allowance.json").write_text(
        json.dumps({"enabled": True, "remaining": 10, "state": "ok", "unlimited": True}),
        encoding="utf-8",
    )
    focus = focus_ignore.empty_focus()
    focus["repos"] = {
        repo: {"priority": 1, "label": "high"} for repo in (
            "SimonBarnett/bobiverse",
            "SimonBarnett/a-search",
        )
    }
    focus["repos"]["SimonBarnett/other"] = {"priority": 9, "label": "low"}
    focus_ignore.save_focus(digest_home, focus)
    focus_ignore.handle_focus_cmd(digest_home, "SimonBarnett/ce-priority#39")
    focus_ignore.handle_focus_cmd(digest_home, "SimonBarnett/trutex#33")
    _queue(
        digest_home,
        [
            _row(repo="SimonBarnett/bobiverse", num=5186),
            _row(repo="SimonBarnett/a-search", num=5058),
            _row(repo="SimonBarnett/agentic_fomprep", num=237),
            _row(repo="SimonBarnett/a-search", num=5139, needs_human=True),
            _row(repo="SimonBarnett/a-search", num=5170, labels=["on-hold"]),
            _row(repo="SimonBarnett/a-search", num=5221, require_machine="redqueen"),
            _row(repo="SimonBarnett/ce-priority", num=39),
            _row(repo="SimonBarnett/trutex", num=33),
            _row(repo="SimonBarnett/other", num=1),
            _row(repo="SimonBarnett/unfocused", num=2),
        ],
    )
    posts: list[str] = []

    def fake_gh(method, url, body=None):
        if "copilot_internal/user" in url:
            return UNLIMITED, 200
        if str(method).upper() == "POST" and "/tasks" in str(url):
            posts.append(str(url))
            task_id = f"task-{len(posts)}"
            return {"id": task_id, "html_url": f"https://github.com/tasks/{task_id}"}, 201
        return {}, 200

    chair = ch.ChairJobs(
        chair_home,
        digest_home,
        log=lambda _line: None,
        spawn=False,
        token_loader=lambda: ("test-token", "test"),
        clock=lambda: 1_000_000.0,
    )
    monkeypatch.setattr(chair, "_github_json", fake_gh)

    for _ in range(3):
        chair._copilot_tick()

    assert len(posts) == 2
    assert {
        url.split("/agents/repos/", 1)[1].split("/tasks", 1)[0] for url in posts
    } == {
        "SimonBarnett/bobiverse",
        "SimonBarnett/a-search",
    }
    remaining = gitclaim.load_unaccepted(digest_home)
    assert {row["id"] for row in remaining} == {
        "#237", "#5139", "#5170", "#5221", "#39", "#33", "#1", "#2"
    }
