"""FR #5170: Copilot virtual seat + webhook-first queue (resync fallback)."""
from __future__ import annotations

from pathlib import Path

import bobreport
import chair_health
import copilot_dispatch as cd
import focus_ignore as fi
import gitclaim
import shop_listen


REPO = "SimonBarnett/bobiverse"


def _row(task="FR", num=10, **extra):
    row = {
        "repo": REPO,
        "task": task,
        "id": f"#{num}",
        "url": f"https://github.com/{REPO}/issues/{num}",
        "title": "do the thing",
    }
    row.update(extra)
    return row


def test_build_task_body_uses_prompt_not_problem_statement():
    for task in ("FR", "FIX", "MRB"):
        body = cd.build_task_body(_row(task=task, num=3 if task != "MRB" else 3))
        assert "prompt" in body
        assert "problem_statement" not in body
        assert task in body["prompt"]
        assert REPO in body["prompt"]


def test_tasks_api_path():
    assert cd.tasks_api_path(REPO) == "agents/repos/SimonBarnett/bobiverse/tasks"


def test_exhaustion_stops_and_resumes(tmp_path):
    fi.handle_focus_cmd(tmp_path, f"high {REPO}")
    cd.set_allowance(tmp_path, remaining=5)
    assert cd.has_allowance(tmp_path)
    assert cd.is_exhausted({"status": 403, "message": "quota exceeded"})
    cd.record_api_result(tmp_path, {"status": 403, "message": "Copilot allowance exhausted"})
    assert not cd.has_allowance(tmp_path)
    # IRC fallback: dispatch returns exhausted, job stays unaccepted
    claim = gitclaim.GitClaim(
        repo=REPO, task="FR", id="#10", event="issues", action="opened", line="x"
    )
    gitclaim.apply_queue_event(tmp_path, claim)
    out = cd.dispatch_row(tmp_path, _row(), post=lambda *_a, **_k: {"status": 403, "message": "quota"})
    assert out["status"] == "exhausted"
    assert any(r.get("id") == "#10" for r in gitclaim.load_unaccepted(tmp_path))
    cd.set_allowance(tmp_path, remaining=2)
    assert cd.has_allowance(tmp_path)


def test_parse_mrb_verdict():
    assert cd.parse_mrb_verdict("MRB PASS\n## MRB board\n**Verdict:** PASS") == "PASS"
    assert cd.parse_mrb_verdict("MRB FAIL https://example") == "FAIL"
    assert cd.parse_mrb_verdict("looks good to me") is None
    assert cd.parse_mrb_verdict("") is None


def test_no_self_mrb_copilot():
    row = _row(task="MRB", num=99, author_seat="copilot", url=f"https://github.com/{REPO}/pull/99")
    assert cd.should_dispatch(row, allowance=True) is False
    assert gitclaim.review_blocked_for_author(row, "copilot", live={"copilot"}) is True


def test_timeout_giveup_requeues(tmp_path):
    gitclaim.apply_queue_event(
        tmp_path,
        gitclaim.GitClaim(repo=REPO, task="FR", id="#11", event="issues", action="opened", line="x"),
    )
    shop_listen.accept_job_by_ref(
        tmp_path, nick="copilot", channel="#bobiverse", repo=REPO, task="FR", ident="#11", title="t"
    )
    job = {
        "repo": REPO,
        "task": "FR",
        "id": "#11",
        "started": 0.0,
        "task_id": "abc",
    }
    out = cd.handle_timeout_or_fail(tmp_path, job, now=cd.TASK_TIMEOUT_S + 1, reason="timeout")
    assert out["status"] in ("giveup", "requeue")
    seats = " ".join(
        str(r.get("giveup_seats") or "") for r in gitclaim.load_unaccepted(tmp_path)
    ).lower()
    assert "copilot" in seats or any(
        r.get("id") == "#11" for r in gitclaim.load_unaccepted(tmp_path)
    )


def test_announcements_match_seat_wording():
    hand = cd.announce_handoff(
        repo=REPO, task="FR", ident="#10", task_url="https://github.com/orgs/x/tasks/1"
    )
    assert "copilot" in hand.lower()
    assert REPO in hand
    assert "FR" in hand
    assert "#10" in hand or "10" in hand
    assert "tasks/" in hand
    done = cd.announce_complete(
        repo=REPO, task="MRB", ident="#9", result="PASS", pr_url=f"https://github.com/{REPO}/pull/9"
    )
    assert "DONE" in done or "PASS" in done
    assert "copilot" in done.lower()
    fail = cd.announce_complete(
        repo=REPO, task="FR", ident="#8", result="timeout", pr_url="", reason="timeout"
    )
    assert "timeout" in fail.lower()


def test_ensure_webhook_create_repair_ok_noperm(tmp_path):
    created = []
    patched = []

    def list_ok(_repo):
        return [
            {
                "id": 1,
                "active": True,
                "events": list(cd.REQUIRED_HOOK_EVENTS),
                "config": {"url": cd.GIT_HOOK_URL},
            }
        ]

    r = cd.ensure_repo_webhook(REPO, list_hooks=list_ok, create=created.append, patch=patched.append)
    assert r["action"] == "ok"
    assert created == [] and patched == []

    def list_missing(_repo):
        return []

    r = cd.ensure_repo_webhook(
        REPO, list_hooks=list_missing, create=lambda h: created.append(h) or {"id": 2}, patch=patched.append
    )
    assert r["action"] == "create"
    assert created and set(created[-1]["events"]) >= set(cd.REQUIRED_HOOK_EVENTS)

    def list_wrong(_repo):
        return [{"id": 3, "active": True, "events": ["push"], "config": {"url": cd.GIT_HOOK_URL}}]

    r = cd.ensure_repo_webhook(
        REPO, list_hooks=list_wrong, create=created.append, patch=lambda hid, body: patched.append((hid, body))
    )
    assert r["action"] == "repair"
    assert patched

    def list_boom(_repo):
        raise PermissionError("no hooks")

    stalls = []
    r = cd.ensure_repo_webhook(
        REPO,
        list_hooks=list_boom,
        create=created.append,
        patch=patched.append,
        file_stall=lambda **kw: stalls.append(kw),
    )
    assert r["action"] == "stall"
    assert stalls


def test_queue_from_webhooks_no_resync(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    resync_calls = []
    monkeypatch.setattr(gitclaim, "resync_from_github", lambda *a, **k: resync_calls.append(1))

    opened = {
        "action": "opened",
        "repository": {"full_name": REPO},
        "issue": {
            "number": 70,
            "title": "FR: widget",
            "body": "need widget",
            "state": "open",
            "labels": [{"name": "feature-request"}],
        },
    }
    out = bobreport.apply_git_webhook(tmp_path, "issues", opened)
    assert out.ok
    assert any(r.get("id") == "#70" for r in gitclaim.load_unaccepted(tmp_path))

    pr = {
        "action": "opened",
        "repository": {"full_name": REPO},
        "pull_request": {
            "number": 71,
            "title": "fr 70",
            "body": f"Closes {REPO}#70",
            "merged": False,
            "draft": False,
            "state": "open",
            "html_url": f"https://github.com/{REPO}/pull/71",
            "labels": [],
        },
    }
    assert bobreport.apply_git_webhook(tmp_path, "pull_request", pr).ok
    sync = dict(pr)
    sync["action"] = "synchronize"
    assert bobreport.apply_git_webhook(tmp_path, "pull_request", sync).ok
    closed = dict(pr)
    closed["action"] = "closed"
    closed["pull_request"] = dict(pr["pull_request"], merged=True)
    assert bobreport.apply_git_webhook(tmp_path, "pull_request", closed).ok

    review = {
        "action": "submitted",
        "repository": {"full_name": REPO},
        "pull_request": {"number": 71, "html_url": f"https://github.com/{REPO}/pull/71"},
        "review": {"state": "approved", "body": "ok"},
    }
    assert bobreport.apply_git_webhook(tmp_path, "pull_request_review", review).ok
    cr = {
        "action": "completed",
        "repository": {"full_name": REPO},
        "check_run": {
            "name": "ci",
            "status": "completed",
            "conclusion": "success",
            "html_url": "https://example/run",
        },
        "check_suite": {},
    }
    assert bobreport.apply_git_webhook(tmp_path, "check_run", cr).ok
    wr = {
        "action": "completed",
        "repository": {"full_name": REPO},
        "workflow_run": {
            "id": 1,
            "status": "completed",
            "conclusion": "success",
            "html_url": "https://example/wf",
            "head_sha": "abc",
        },
    }
    assert bobreport.apply_git_webhook(tmp_path, "workflow_run", wr).ok
    assert resync_calls == []


def test_resync_only_on_fallback():
    assert cd.resync_is_fallback("startup") is True
    assert cd.resync_is_fallback("webhook_gap") is True
    assert cd.resync_is_fallback("delivery_failure") is True
    assert cd.resync_is_fallback("safety_interval") is True
    assert cd.resync_is_fallback("operator") is True
    assert cd.resync_is_fallback("normal") is False
    assert chair_health.RESYNC_S >= 3600.0


def test_dispatch_posts_and_accepts(tmp_path):
    fi.handle_focus_cmd(tmp_path, f"high {REPO}")
    gitclaim.apply_queue_event(
        tmp_path,
        gitclaim.GitClaim(repo=REPO, task="FR", id="#12", event="issues", action="opened", line="x"),
    )
    cd.set_allowance(tmp_path, remaining=3)
    posts = []

    def post(path, body):
        posts.append((path, body))
        return {"status": 201, "id": "task-1", "html_url": "https://github.com/tasks/1"}

    out = cd.dispatch_row(tmp_path, _row(num=12), post=post)
    assert out["status"] == "dispatched"
    assert posts and "prompt" in posts[0][1]
    acc = gitclaim.load_accepted(tmp_path)
    assert any(r.get("nick") == "copilot" and r.get("id") == "#12" for r in acc)


def test_copilot_comment_completes_mrb(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim.apply_queue_event(
        tmp_path,
        gitclaim.GitClaim(repo=REPO, task="MRB", id="#20", event="pull_request", action="opened", line="x"),
    )
    shop_listen.accept_job_by_ref(
        tmp_path, nick="copilot", channel="#bobiverse", repo=REPO, task="MRB", ident="#20", title="t"
    )
    payload = {
        "action": "created",
        "repository": {"full_name": REPO},
        "issue": {
            "number": 20,
            "pull_request": {"url": f"https://api.github.com/repos/{REPO}/pulls/20"},
            "html_url": f"https://github.com/{REPO}/pull/20",
        },
        "comment": {"body": "MRB PASS\n**Verdict:** PASS", "user": {"login": "copilot-swe-agent"}},
    }
    cd.handle_issue_comment(tmp_path, payload)
    done = list(gitclaim.load_queue(tmp_path).get("done") or [])
    assert any(r.get("id") == "#20" and str(r.get("result") or "").upper() == "PASS" for r in done)
