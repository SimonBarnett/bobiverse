"""FR #4854: resync MRB author_seat must not come from a Refs issue with a different result PR.

When a PR body has Closes #A and Refs #B, and FR #B was done by seat X with a *different*
result PR, the resync MRB row must not stamp X as author_seat / implementer_seat, and X
must remain offerable for that MRB. Prefer the DONE FR whose result URL is this PR.
"""
from __future__ import annotations

import bobreport
import gitclaim
import registered_machines


REPO = "SimonBarnett/a-search"
PR_A = "https://github.com/SimonBarnett/a-search/pull/4465"
PR_B = "https://github.com/SimonBarnett/a-search/pull/4449"
SEAT_OPENER = "marchhare-18124"  # DONE FR #4451 -> PR #4465
SEAT_REFS = "flamingo-37200"  # DONE FR #4448 -> PR #4449 (Refs only on #4465)
SEAT_OTHER = "flamingo-48824"


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare", "flamingo", "ionos"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["workers"] = {
        "18124": {"state": "idle", "nick": SEAT_OPENER},
    }
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["workers"] = {
        "37200": {"state": "idle", "nick": SEAT_REFS},
        "48824": {"state": "idle", "nick": SEAT_OTHER},
    }
    bobreport.save_digest(tmp_path, digest)
    return tmp_path


def _fetch_pr_4465(url: str):
    if "/pulls" in url and "state=closed" not in url:
        return [
            {
                "number": 4465,
                "title": "fix(search): AWS fan-out",
                "body": (
                    "Closes SimonBarnett/a-search#4451\n"
                    "Refs SimonBarnett/a-search#4448\n"
                ),
                "html_url": PR_A,
                "state": "open",
                "user": {"login": "u"},
                "draft": False,
            }
        ]
    if "/issues" in url:
        return []
    return []


def test_resync_mrb_author_from_closes_result_not_refs_done_by(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [],
            "done": [
                {
                    "repo": REPO,
                    "task": "FR",
                    "id": "#4448",
                    "seq": 1,
                    "nick": SEAT_REFS,
                    "done_by": SEAT_REFS,
                    "ts": "t",
                    "line": "x",
                    "channel": "#flamingo",
                    "result": PR_B,
                    "url": PR_B,
                    "done_ts": "t",
                },
                {
                    "repo": REPO,
                    "task": "FR",
                    "id": "#4451",
                    "seq": 2,
                    "nick": SEAT_OPENER,
                    "done_by": SEAT_OPENER,
                    "ts": "t",
                    "line": "x",
                    "channel": "#marchhare",
                    "result": PR_A,
                    "url": PR_A,
                    "done_ts": "t",
                },
            ],
        },
    )

    res = gitclaim.resync_from_github(home, [REPO], fetch_json=_fetch_pr_4465)
    assert res.get("ok") is True
    mrbs = [
        r
        for r in gitclaim.load_unaccepted(home)
        if str(r.get("task") or "").upper() == "MRB" and str(r.get("id")) == "#4465"
    ]
    assert len(mrbs) == 1, mrbs
    row = mrbs[0]
    assert row.get("author_seat") != SEAT_REFS, row
    assert row.get("implementer_seat") != SEAT_REFS, row
    assert row.get("author_seat") == SEAT_OPENER, row
    assert row.get("implementer_seat") == SEAT_OPENER, row

    # Refs seat must still be offerable for the hostile MRB.
    st, job = gitclaim.offer_focus_top(home, SEAT_REFS, "#flamingo")
    assert st == "ok", (st, job)
    assert job and str(job.get("id")) == "#4465"


def test_mrb_author_extra_skips_refs_fr_with_different_result_pr(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    doc = {
        "v": 1,
        "unaccepted": [],
        "accepted": [],
        "done": [
            {
                "repo": REPO,
                "task": "FR",
                "id": "#4448",
                "done_by": SEAT_REFS,
                "nick": SEAT_REFS,
                "url": PR_B,
                "result": PR_B,
            },
            {
                "repo": REPO,
                "task": "FR",
                "id": "#4451",
                "done_by": SEAT_OPENER,
                "nick": SEAT_OPENER,
                "url": PR_A,
                "result": PR_A,
            },
        ],
    }
    claim = gitclaim.GitClaim(
        repo=REPO,
        task="MRB",
        id="#4465",
        event="pull_request",
        action="opened",
        line="",
        refs=("#4451", "#4448"),
        title="fix",
        body="Closes #4451\nRefs #4448",
    )
    extra = gitclaim.mrb_author_extra_from_doc(doc, claim)
    assert extra.get("author_seat") == SEAT_OPENER, extra
    assert extra.get("implementer_seat") == SEAT_OPENER, extra
