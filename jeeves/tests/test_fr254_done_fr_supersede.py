"""FR #254: after DONE FR with PR URL, do not re-offer that FR while superseding MRB exists."""
from __future__ import annotations

import bobreport
import gitclaim
import registered_machines
import shop_listen


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare", "ionos", "flamingo"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def test_parse_github_pull_url():
    assert gitclaim.parse_github_pull_url(
        "https://github.com/SimonBarnett/gh-Jeeves/pull/227"
    ) == ("SimonBarnett/gh-Jeeves", "#227")
    assert gitclaim.parse_github_pull_url(
        "https://github.com/SimonBarnett/bobiverse/pull/240/"
    ) == ("SimonBarnett/bobiverse", "#240")
    assert gitclaim.parse_github_pull_url("https://example/nope") is None


def test_done_fr_queues_mrb_on_pr_repo_and_supersedes_fr(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#224",
                "seq": 1,
                "ts": "t",
                "line": "x",
            }
        ],
        "accepted": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#224",
                "seq": 1,
                "nick": "marchhare-41912",
                "ts": "t",
                "line": "x",
                "channel": "#marchhare",
                "accepted_ts": "t",
            }
        ],
        "done": [],
    }
    gitclaim._write_queue(gitclaim.queue_path(home), doc)
    st, job = shop_listen.complete_job_by_ref(
        home,
        repo="SimonBarnett/bobiverse",
        task="FR",
        ident="#224",
        nick="marchhare-41912",
        result="",
        url="https://github.com/SimonBarnett/gh-Jeeves/pull/227",
    )
    assert st == "ok"
    rows = gitclaim.load_unaccepted(home)
    assert not any(r.get("task") == "FR" and r.get("id") == "#224" for r in rows)
    mrbs = [r for r in rows if r.get("task") == "MRB"]
    assert len(mrbs) == 1
    assert mrbs[0]["repo"] == "SimonBarnett/gh-Jeeves"
    assert mrbs[0]["id"] == "#227"
    assert "#224" in (mrbs[0].get("refs") or [])
    assert mrbs[0].get("supersedes") == "SimonBarnett/bobiverse#224"
    assert mrbs[0].get("author_seat") == "marchhare-41912"


def test_offer_skips_fr_while_superseding_mrb_present(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    doc = bobreport.empty_digest()
    doc["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    doc["machines"]["marchhare"]["workers"] = {"41928": {"state": "idle"}}
    bobreport.save_digest(home, doc)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#224",
                    "seq": 1,
                    "ts": "t",
                    "line": "x",
                },
                {
                    # FR #785: use a live repo here — archived gh-Jeeves rows are never offered.
                    "repo": "SimonBarnett/bobiverse",
                    "task": "MRB",
                    "id": "#227",
                    "seq": 2,
                    "ts": "t",
                    "line": "x",
                    "refs": ["#224"],
                    "supersedes": "SimonBarnett/bobiverse#224",
                    # FR #595: real pull URL required (never invent from issue id).
                    "url": "https://github.com/SimonBarnett/bobiverse/pull/227",
                },
            ],
            "accepted": [],
            "done": [],
        },
    )
    st, job = gitclaim.offer_focus_top(home, "marchhare-41928", "#marchhare")
    assert st == "ok"
    assert job["task"] == "MRB"
    assert job["id"] == "#227"


def test_resync_does_not_readd_fr_superseded_by_mrb(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/gh-Jeeves",
                    "task": "MRB",
                    "id": "#227",
                    "seq": 1,
                    "ts": "t",
                    "line": "x",
                    "refs": ["#224"],
                    "supersedes": "SimonBarnett/bobiverse#224",
                }
            ],
            "accepted": [],
            "done": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#224",
                    "nick": "marchhare-41912",
                    "url": "https://github.com/SimonBarnett/gh-Jeeves/pull/227",
                    "done_ts": "t",
                }
            ],
        },
    )

    def fetch(url: str):
        if "/issues?" in url and "bobiverse" in url:
            return [
                {
                    "number": 224,
                    "title": "requeue gap",
                    "body": "x",
                    "labels": [{"name": "via-intake"}],
                    "state": "open",
                }
            ]
        if "/pulls?" in url and "bobiverse" in url:
            return []
        if "gh-Jeeves" in url and "/pulls?" in url:
            return [
                {
                    "number": 227,
                    "title": "fix",
                    "body": "Implements SimonBarnett/bobiverse#224",
                }
            ]
        if "gh-Jeeves" in url and "/issues?" in url:
            return []
        return []

    out = gitclaim.resync_from_github(
        home,
        ["SimonBarnett/bobiverse", "SimonBarnett/gh-Jeeves"],
        fetch_json=fetch,
    )
    assert out.get("ok") is True
    frs = [
        r
        for r in gitclaim.load_unaccepted(home)
        if r.get("task") == "FR" and r.get("id") == "#224" and r.get("repo") == "SimonBarnett/bobiverse"
    ]
    assert frs == []


def test_resync_does_not_readd_fr_when_done_fr_has_open_pr_url(tmp_path, monkeypatch):
    """Even if MRB row was dropped, done FR with /pull/ URL keeps the issue superseded."""
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [],
            "done": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#224",
                    "nick": "marchhare-41912",
                    "url": "https://github.com/SimonBarnett/gh-Jeeves/pull/227",
                    "done_ts": "t",
                }
            ],
        },
    )

    def fetch(url: str):
        if "/issues?" in url:
            return [
                {
                    "number": 224,
                    "title": "still open",
                    "body": "x",
                    "labels": [{"name": "via-intake"}],
                    "state": "open",
                }
            ]
        return []

    out = gitclaim.resync_from_github(home, ["SimonBarnett/bobiverse"], fetch_json=fetch)
    assert out.get("ok") is True
    assert gitclaim.load_unaccepted(home) == []


def test_append_fr_skipped_when_superseded(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/gh-Jeeves",
                    "task": "MRB",
                    "id": "#227",
                    "seq": 1,
                    "ts": "t",
                    "line": "x",
                    "supersedes": "SimonBarnett/bobiverse#224",
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    claim = gitclaim.GitClaim(
        repo="SimonBarnett/bobiverse",
        task="FR",
        id="#224",
        event="issues",
        action="opened",
        line="x",
        title="gap",
    )
    assert gitclaim.apply_queue_event(home, claim) in ("noop", "skipped", "duplicate")
    assert not any(r.get("task") == "FR" for r in gitclaim.load_unaccepted(home))


def test_offer_skips_fr_when_only_done_fr_has_pull_url(tmp_path, monkeypatch):
    """Hostile MRB #275: no MRB row left, but DONE FR URL must still block re-offer."""
    home = _home(tmp_path, monkeypatch)
    doc = bobreport.empty_digest()
    doc["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    doc["machines"]["marchhare"]["workers"] = {"35600": {"state": "idle"}}
    bobreport.save_digest(home, doc)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#224",
                    "seq": 1,
                    "ts": "t",
                    "line": "x",
                },
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#10",
                    "seq": 2,
                    "ts": "t",
                    "line": "other",
                },
            ],
            "accepted": [],
            "done": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#224",
                    "nick": "marchhare-41912",
                    "url": "https://github.com/SimonBarnett/gh-Jeeves/pull/227",
                    "done_ts": "t",
                }
            ],
        },
    )
    st, job = gitclaim.offer_focus_top(home, "marchhare-35600", "#marchhare")
    assert st == "ok"
    assert job["id"] == "#10"
    assert job["task"] == "FR"


def test_done_fr_not_superseded_when_pr_closed_and_repo_fetched():
    """When implement PR repo was fetched and PR is no longer open, do not block."""
    doc = {
        "done": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#224",
                "url": "https://github.com/SimonBarnett/gh-Jeeves/pull/227",
            }
        ],
        "unaccepted": [],
        "accepted": [],
    }
    assert (
        gitclaim.fr_superseded_by_done_pr(
            doc,
            "SimonBarnett/bobiverse",
            "#224",
            open_pulls={"SimonBarnett/gh-Jeeves": set()},
            fetched_repos={"SimonBarnett/gh-Jeeves"},
        )
        is False
    )
    assert (
        gitclaim.fr_superseded_by_done_pr(
            doc,
            "SimonBarnett/bobiverse",
            "#224",
            open_pulls={"SimonBarnett/gh-Jeeves": {"#227"}},
            fetched_repos={"SimonBarnett/gh-Jeeves"},
        )
        is True
    )


def test_load_queue_preserves_done_pull_url(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [],
            "done": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#224",
                    "url": "https://github.com/SimonBarnett/gh-Jeeves/pull/227",
                    "done_ts": "t",
                    "done_by": "marchhare-41912",
                }
            ],
        },
    )
    loaded = gitclaim.load_queue(home)
    done = loaded.get("done") or []
    assert len(done) == 1
    assert done[0]["url"].endswith("/pull/227")
    assert done[0].get("done_by") == "marchhare-41912"
