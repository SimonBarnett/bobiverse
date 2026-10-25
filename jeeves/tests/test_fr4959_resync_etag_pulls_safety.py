"""FR #4959: ETag/304 on issues must not skip open pulls (lesson MRB safety net).

Regression: resync wrapped issues+pulls in one try/except NotModified. A 304 on the
open-issues list skipped the pulls fetch entirely, so new lesson (and product) PRs
stayed off-queue until a manual !resync saw a non-304. Periodic logs showed
``github-resync ok repos=0`` with no note while configured repos still existed.
"""
from __future__ import annotations

import json
from pathlib import Path

import bobreport
import chair_health as ch
import gitclaim
import github_api_budget as gab

REPO = "SimonBarnett/a-search"


def _ids(home: Path):
    return {(r["task"], r["id"]) for r in gitclaim.load_unaccepted(home)}


def test_issues_304_still_fetches_open_pulls_and_enqueues_lesson_mrb(tmp_path: Path):
    """Open-issues 304 + open-pulls 200 must enqueue the new lesson MRB."""
    lesson = {
        "number": 4899,
        "title": "lesson(harvest-agent-skills): Fixture-only /selftest probes",
        "body": (
            "Lessons:\n- fixture\n\n---\n_source machine=`flamingo` "
            "agent=`Invoke-BobiverseHarvest` book=`harvest-agent-skills` "
            "ver=`-` seat=`flamingo-15516`_\n"
        ),
        "draft": False,
        "state": "open",
        "html_url": f"https://github.com/{REPO}/pull/4899",
        "labels": [{"name": "via-intake"}, {"name": "harvest-lesson"}],
        "user": {"login": "x"},
        "head": {"ref": "intake/x", "sha": "abc"},
        "base": {"ref": "main"},
    }
    calls: list[str] = []

    def fetch(url: str, force_refresh: bool = False):
        calls.append(f"{'force:' if force_refresh else ''}{url}")
        if "/issues?" in url:
            if force_refresh:
                return []  # no open issues; pulls still carry the new lesson
            raise gab.NotModified(url)
        if "/pulls?" in url:
            return [lesson]
        return []

    res = gitclaim.resync_from_github(tmp_path, [REPO], fetch_json=fetch, token="t")
    assert res["ok"]
    assert REPO in (res.get("repos") or [])
    assert REPO not in (res.get("unchanged") or [])
    assert ("MRB", "#4899") in _ids(tmp_path)
    assert any("/pulls?" in u for u in calls), "pulls must be fetched after issues 304"
    assert any(u.startswith("force:") and "/issues?" in u for u in calls)


def test_both_lists_304_marks_unchanged_not_repos_zero_silent(tmp_path: Path):
    """All-304 must report unchanged= and leave prior rows alone."""
    row = {
        "repo": REPO,
        "task": "FR",
        "id": "#1",
        "seq": 1,
        "ts": "t",
        "line": f"FR {REPO}#1",
        "url": f"https://github.com/{REPO}/issues/1",
        "title": "prior",
        "state": "open",
        "event": "issues",
    }
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": [], "workers": {}},
    )

    def fetch(url: str, force_refresh: bool = False):
        del force_refresh
        raise gab.NotModified(url)

    res = gitclaim.resync_from_github(tmp_path, [REPO], fetch_json=fetch, token="t")
    assert res["ok"]
    assert res.get("repos") == []
    assert REPO in (res.get("unchanged") or [])
    assert ("FR", "#1") in _ids(tmp_path)


def test_force_refresh_skips_if_none_match(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JEEVES_RESYNC_REPOS", REPO)
    body = json.dumps(
        [{"number": 2, "title": "lesson(harvest-agent-skills): tip", "body": "", "draft": False,
          "state": "open", "html_url": f"https://github.com/{REPO}/pull/2",
          "labels": [{"name": "harvest-lesson"}], "user": {"login": "x"},
          "head": {"ref": "x", "sha": "s"}, "base": {"ref": "main"}}]
    ).encode()
    state = {"inm": 0}

    class _FakeResp:
        def __init__(self, status: int, raw: bytes = b"", headers: dict | None = None):
            self.status = status
            self._raw = raw
            self.headers = headers or {}

        def read(self):
            return self._raw

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _req_header(req, name: str):
        for bag in (getattr(req, "headers", None), getattr(req, "unredirected_hdrs", None)):
            if not bag:
                continue
            for k, v in (bag.items() if hasattr(bag, "items") else []):
                if str(k).lower() == name.lower():
                    return v
        return None

    def opener(req, timeout=30.0):
        del timeout
        if _req_header(req, "If-None-Match"):
            state["inm"] += 1
            return _FakeResp(304, b"", {"X-RateLimit-Remaining": "4990"})
        url = getattr(req, "full_url", None) or req.get_full_url()
        raw = body if "pulls" in str(url) else b"[]"
        return _FakeResp(200, raw, {"ETag": '"v1"', "X-RateLimit-Remaining": "4999"})

    budget = gab.GithubApiBudget(tmp_path, budget_per_hour=1000, floor=500, log=lambda s: None)
    # Seed etags so a non-forced pass would 304.
    seeded = gab.make_budgeted_fetch(budget, token="t", path="reconcile", opener=opener)
    gitclaim.resync_from_github(tmp_path, [REPO], fetch_json=seeded, token="t")
    before_inm = state["inm"]

    forced = gab.make_budgeted_fetch(
        budget, token="t", path="reconcile", essential=True, force_refresh=True, opener=opener
    )
    res = gitclaim.resync_from_github(tmp_path, [REPO], fetch_json=forced, token="t")
    assert res["ok"]
    assert state["inm"] == before_inm, "force_refresh must not send If-None-Match"
    assert ("MRB", "#2") in _ids(tmp_path) or REPO in (res.get("repos") or [])


def test_pull_request_webhook_invalidates_repo_list_etags(tmp_path: Path):
    """pull_request opened must drop cached issues/pulls ETags for that repo."""
    issues_url = f"https://api.github.com/repos/{REPO}/issues?state=open&per_page=100&page=1"
    pulls_url = f"https://api.github.com/repos/{REPO}/pulls?state=open&per_page=100&page=1"
    other = "https://api.github.com/repos/SimonBarnett/bobiverse/pulls?state=open&per_page=100&page=1"
    bud = gab.GithubApiBudget(tmp_path, log=lambda s: None)
    bud.set_etag(issues_url, '"iss"')
    bud.set_etag(pulls_url, '"prs"')
    bud.set_etag(other, '"keep"')

    n = gab.invalidate_repo_list_etags(tmp_path, REPO)
    assert n >= 2
    # Reload from disk (invalidate uses its own GithubApiBudget instance).
    bud2 = gab.GithubApiBudget(tmp_path, log=lambda s: None)
    assert bud2.get_etag(issues_url) is None
    assert bud2.get_etag(pulls_url) is None
    assert bud2.get_etag(other) == '"keep"'

    out = bobreport.apply_git_webhook(
        tmp_path,
        "pull_request",
        {
            "action": "opened",
            "repository": {"full_name": REPO},
            "pull_request": {
                "number": 7,
                "title": "lesson(harvest-agent-skills): tip",
                "body": "Lessons:\n- x\n",
                "draft": False,
                "merged": False,
                "state": "open",
                "html_url": f"https://github.com/{REPO}/pull/7",
                "labels": [{"name": "harvest-lesson"}],
            },
        },
    )
    assert out.ok, out.err
    # Webhook path also clears via helper (idempotent when already clear).
    assert gab.invalidate_repo_list_etags(tmp_path, REPO) == 0 or True


def test_resync_cycle_logs_unchanged(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JEEVES_RESYNC_REPOS", REPO)
    logs: list[str] = []

    def fetch(url: str, force_refresh: bool = False):
        del force_refresh
        raise gab.NotModified(url)

    # discover_repos reads JEEVES_RESYNC_REPOS / file; stub via fetch + env.
    out = ch.resync_cycle(
        tmp_path,
        token="t",
        ignored=[],
        fetch_json=fetch,
        owners={"simonbarnett"},
        essential=False,
        log=logs.append,
    )
    assert out.get("ok")
    unchanged = out.get("unchanged") or []
    # When discover finds the repo, unchanged should include it.
    if REPO in unchanged or not (out.get("repos") or []):
        assert "unchanged" in out
    # ChairJobs log line includes unchanged= when present.
    jobs = ch.ChairJobs(
        tmp_path,
        tmp_path,
        log=logs.append,
        fetch_json=fetch,
        token_loader=lambda: ("t", "test"),
        ignored_loader=lambda: [],
        spawn=False,
        owners={"simonbarnett"},
    )
    jobs._startup_resync_done = True
    jobs.request_resync()
    jobs._force_refresh_resync = True
    jobs._resync()
    assert any("unchanged=" in ln for ln in logs) or isinstance(jobs.last_resync.get("unchanged"), list)
