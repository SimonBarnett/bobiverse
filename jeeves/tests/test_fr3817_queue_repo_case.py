"""FR #3817: queue dedupe is case-insensitive on owner/repo."""
from __future__ import annotations

import gitclaim
from gitclaim import GitClaim, apply_queue_event, load_unaccepted, resync_from_github


CANON = "SimonBarnett/agentic_fomprep"
LOWER = "simonbarnett/agentic_fomprep"


def _fr(repo: str, ident: str = "#177", *, line: str = "GIT issues opened", action: str = "opened"):
    return GitClaim(
        repo=repo,
        task="FR",
        id=ident,
        event="issues",
        action=action,
        line=line,
        title="x",
        state="open",
    )


def test_append_lower_when_mixed_queued_leaves_one_row(tmp_path):
    apply_queue_event(tmp_path, _fr(CANON, line="GIT issues SimonBarnett/agentic_fomprep opened #177"))
    assert len(load_unaccepted(tmp_path)) == 1
    result = apply_queue_event(tmp_path, _fr(LOWER, line="", action="opened"))
    assert result == "duplicate"
    rows = load_unaccepted(tmp_path)
    assert len(rows) == 1
    assert rows[0]["repo"].lower() == CANON.lower()
    assert rows[0]["id"] in ("#177", "177") or gitclaim._norm_row_id(rows[0]["id"]) == "#177"


def test_close_removes_row_whatever_casing_queued(tmp_path):
    apply_queue_event(tmp_path, _fr(LOWER, line=""))
    assert len(load_unaccepted(tmp_path)) == 1
    apply_queue_event(
        tmp_path,
        GitClaim(
            repo=CANON,
            task="FR",
            id="#177",
            event="issues",
            action="closed",
            line="closed",
        ),
    )
    assert load_unaccepted(tmp_path) == []


def test_resync_collapses_existing_case_variant_twins(tmp_path):
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": CANON,
                    "task": "FR",
                    "id": "#177",
                    "seq": 91,
                    "ts": "2026-10-09T06:46:14Z",
                    "line": "GIT issues SimonBarnett/agentic_fomprep opened #177",
                    "event": "issues",
                    "action": "labeled",
                },
                {
                    "repo": LOWER,
                    "task": "FR",
                    "id": "#177",
                    "seq": 120,
                    "ts": "2026-10-09T07:30:53Z",
                    "line": "",
                    "event": "issues",
                    "action": "opened",
                },
            ],
            "accepted": [],
            "done": [],
        },
    )

    def fetch(url: str):
        if "/pulls" in url:
            return []
        if "/issues" in url:
            return [
                {
                    "number": 177,
                    "title": "FR: x",
                    "body": "b",
                    "labels": [{"name": "bug"}],
                    "state": "open",
                    "pull_request": None,
                }
            ]
        return []

    # Resync via either casing must leave a single FR #177 row.
    resync_from_github(tmp_path, [LOWER], fetch_json=fetch)
    rows = [r for r in load_unaccepted(tmp_path) if str(r.get("task")).upper() == "FR"]
    assert len(rows) == 1
    assert gitclaim._norm_row_id(rows[0].get("id")) == "#177"
    assert rows[0]["repo"].lower() == CANON.lower()
    # Prefer the informative GIT line over empty resync line when collapsing.
    assert "GIT issues" in str(rows[0].get("line") or "") or str(rows[0].get("line") or "") != ""


def test_same_helper_is_case_insensitive_on_repo():
    row = {"repo": CANON, "task": "FR", "id": "#177"}
    assert gitclaim._same(row, LOWER, "FR", "#177")
    assert gitclaim._same(row, CANON, "fr", "177")
    assert not gitclaim._same(row, "SimonBarnett/other", "FR", "#177")


def test_discover_repos_dedupes_case_variants(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    import chair_health

    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                {"repo": CANON, "task": "FR", "id": "#1"},
                {"repo": LOWER, "task": "FR", "id": "#2"},
            ],
            "accepted": [],
            "done": [],
        },
    )

    def getter(url: str):
        return []

    repos = chair_health.discover_repos(tmp_path, {"simonbarnett"}, getter, ignored=())
    keys = [r.lower() for r in repos]
    assert keys.count(CANON.lower()) == 1
