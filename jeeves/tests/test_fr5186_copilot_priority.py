"""FR #5186: dispatch only high-priority, offerable jobs through chair wiring."""
from __future__ import annotations

import focus_ignore
import gitclaim
import copilot_dispatch as cd
import chair_health as ch


UNLIMITED = {
    "copilot_plan": "business",
    "quota_snapshots": {
        "premium_interactions": {
            "remaining": 0,
            "unlimited": True,
            "overage_permitted": True,
        }
    },
}


def _row(repo, num, **extra):
    row = {
        "repo": repo,
        "task": "FR",
        "id": f"#{num}",
        "url": f"https://github.com/{repo}/issues/{num}",
        "title": "do the thing",
        "event": "issues",
        "action": "opened",
    }
    row.update(extra)
    return row


def _queue(home, rows):
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": rows, "accepted": [], "done": []},
    )


def test_real_chair_dispatches_only_high_unblocked_jobs(tmp_path, monkeypatch):
    digest_home = tmp_path / "digest"
    chair_home = tmp_path / "chair"
    digest_home.mkdir()
    chair_home.mkdir()
    monkeypatch.setenv("BOB_DIGEST_HOME", str(digest_home))
    focus_ignore.handle_focus_cmd(digest_home, "high SimonBarnett/bobiverse")
    focus_ignore.handle_focus_cmd(digest_home, "high SimonBarnett/a-search")
    focus_ignore.handle_focus_cmd(digest_home, "high SimonBarnett/ce-priority")
    focus_ignore.handle_focus_cmd(digest_home, "high SimonBarnett/trutex")

    rows = [
        _row("SimonBarnett/a-search", 5058),
        _row("SimonBarnett/bobiverse", 5181),
        _row("SimonBarnett/ce-priority", 39),
        _row("SimonBarnett/trutex", 33),
        _row("SimonBarnett/a-search", 5059, labels=["hold"]),
        _row("SimonBarnett/a-search", 5060, needs_human=True),
        _row("SimonBarnett/a-search", 5061, require_machine="ionos"),
    ]
    _queue(digest_home, rows)

    posted_repos = []
    task_number = 0

    def fake_github_json(method, url, body=None):
        nonlocal task_number
        if url.endswith("/copilot_internal/user"):
            return UNLIMITED, 200
        if method == "POST" and url.endswith("/tasks"):
            task_number += 1
            posted_repos.append(url.split("/repos/", 1)[1].split("/tasks", 1)[0])
            return {"id": f"task-{task_number}", "html_url": f"https://example/{task_number}"}, 201
        raise AssertionError(f"unexpected GitHub request: {method} {url}")

    chair = ch.ChairJobs(
        chair_home,
        digest_home,
        log=lambda _line: None,
        spawn=False,
        token_loader=lambda: ("test-token", "test"),
        fetch_json=None,
        announce=lambda _line: None,
    )
    chair._github_json = fake_github_json

    chair._copilot_tick()
    chair._copilot_tick()

    assert set(posted_repos) == {
        "SimonBarnett/bobiverse",
        "SimonBarnett/a-search",
    }
    accepted_repos = {
        row["repo"]
        for row in gitclaim.load_accepted(digest_home)
        if row.get("nick") == cd.COPILOT_NICK
    }
    assert accepted_repos == set(posted_repos)
    still_queued = {(row["repo"], row["id"]) for row in gitclaim.load_unaccepted(digest_home)}
    for repo, ident in (
        ("SimonBarnett/ce-priority", "#39"),
        ("SimonBarnett/trutex", "#33"),
        ("SimonBarnett/a-search", "#5059"),
        ("SimonBarnett/a-search", "#5060"),
        ("SimonBarnett/a-search", "#5061"),
    ):
        assert (repo, ident) in still_queued


def test_item_focus_does_not_make_another_repo_copilot_eligible(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    focus_ignore.handle_focus_cmd(tmp_path, "1 SimonBarnett/ce-priority#39")
    row = _row("SimonBarnett/ce-priority", 39)

    assert focus_ignore.offer_sort_key(tmp_path, row)[1] == 1
    assert cd.is_high_priority(tmp_path, row) is False
    assert cd.should_dispatch(row, allowance=True, home=tmp_path) is False


def test_held_body_and_needs_human_are_not_dispatchable(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    focus_ignore.handle_focus_cmd(tmp_path, "high SimonBarnett/a-search")

    held = _row("SimonBarnett/a-search", 5059, body="HOLD: Simon requested a pause.")
    needs_human = _row("SimonBarnett/a-search", 5060, needs_human=True)

    assert cd.should_dispatch(held, allowance=True, home=tmp_path) is False
    assert cd.should_dispatch(needs_human, allowance=True, home=tmp_path) is False
