"""FR #7118: !assign MRB / !resync queue open non-draft intake/ harvest PRs.

Live shapes (13 Nov 2026): bobiverse#6828 and #6797 — intake/in_* heads,
via-intake+skill, docs/intake-harvest-only files, ready_for_review.
Webhook still skips harvest receipts (FR #2650); chair enqueue and resync must not.
"""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim

REPO = "SimonBarnett/bobiverse"
NICK = "flamingo-8508"

PR_6828 = {
    "number": 6828,
    "title": "docs/mrb push: HEAD:branch not stale local name",
    "body": (
        "MRB #6809: local branch docs/mrb-6809-hostile created earlier from origin/main.\n"
        "---\n"
        "_via-intake id=`in_ffc2ee825d1b4c98` ts=`2026-11-12T13:05:43Z`_\n"
        "_source machine=`redqueen` agent=`Report-BobiverseIntakeIssue` book=`harvest` ver=`-`_\n"
    ),
    "state": "open",
    "draft": False,
    "html_url": f"https://github.com/{REPO}/pull/6828",
    "pull_request": {},
    "labels": [{"name": "via-intake"}, {"name": "skill"}],
    "head": {"ref": "intake/in_ffc2ee825d1b4c98", "sha": "a" * 40},
    "files": [{"filename": "docs/intake-harvest/intake-in_ffc2ee825d1b4c98.md"}],
}

PR_6797 = {
    "number": 6797,
    "title": "FR-04 Groups table is jeeves/docs not repo-root docs/",
    "body": (
        "FR #6752 cited docs/feature-request-jeeves-appliance-ui-2026-11-12.md.\n"
        "---\n"
        "_via-intake id=`in_7e9c0f81cc744a2b` ts=`2026-11-12T12:47:52Z`_\n"
        "_source machine=`flamingo` agent=`Report-BobiverseIntakeIssue` book=`harvest` ver=`-`_\n"
    ),
    "state": "open",
    "draft": False,
    "html_url": f"https://github.com/{REPO}/pull/6797",
    "pull_request": {},
    "labels": [{"name": "via-intake"}, {"name": "skill"}],
    "head": {"ref": "intake/in_7e9c0f81cc744a2b", "sha": "b" * 40},
    "files": [{"filename": "docs/intake-harvest/intake-in_7e9c0f81cc744a2b.md"}],
}


def _home(tmp_path: Path) -> Path:
    home = tmp_path / "chair"
    home.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return home


def _register(home: Path, monkeypatch) -> None:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["flamingo"]}', encoding="utf-8"
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    doc = bobreport.empty_digest()
    doc["machines"]["flamingo"] = {
        "id": "flamingo",
        "online": True,
        "working_on": "",
        "worker_list": [{"nick": NICK, "state": "idle", "work": ""}],
        "workers": {"8508": {"pid": "8508", "nick": NICK, "state": "idle"}},
    }
    bobreport.save_digest(home, doc)


def _pr_list_blob(issue: dict) -> dict:
    return {
        "number": issue["number"],
        "title": issue["title"],
        "body": issue["body"],
        "state": "open",
        "draft": False,
        "html_url": issue["html_url"],
        "labels": issue["labels"],
        "head": issue["head"],
        "base": {"ref": "main"},
        "files": issue["files"],
        "mergeable": True,
        "mergeable_state": "clean",
    }


def test_fr7118_shapes_are_receipts_but_open_non_draft():
    for issue in (PR_6828, PR_6797):
        labs = [x["name"] for x in issue["labels"]]
        files = [x["filename"] for x in issue["files"]]
        assert gitclaim.is_intake_harvest_receipt_pr(
            title=issue["title"], body=issue["body"], labels=labs, files=files
        )
        assert issue["draft"] is False
        claim = gitclaim.claim_from_github_issue(REPO, issue)
        assert claim is not None, issue["number"]
        assert claim.task == "MRB"
        assert claim.id == f"#{issue['number']}"


def test_fr7118_enqueue_and_assign_6828(tmp_path: Path, monkeypatch):
    home = _home(tmp_path)
    _register(home, monkeypatch)
    monkeypatch.setattr(gitclaim, "worker_working_on", lambda *a, **k: "")
    monkeypatch.setattr(gitclaim, "live_seat_nicks", lambda h: {NICK})
    monkeypatch.setattr(gitclaim, "free_seat_nicks", lambda h, live: {NICK})
    monkeypatch.setattr(gitclaim, "seat_open_job", lambda *a, **k: "")

    st, job = gitclaim.assign_row(
        home,
        NICK,
        REPO,
        "MRB",
        "6828",
        fetch_issue=lambda r, n: dict(PR_6828),
        pr_exists=lambda r, n: True,
        coderabbit_lookup=lambda *a, **k: None,
    )
    assert st == "ok", job
    assert str(job.get("id")) == "#6828"
    assert str(job.get("offered_to")) == NICK


def test_fr7118_assign_draft_refuses_draft_reason(tmp_path: Path, monkeypatch):
    home = _home(tmp_path)
    _register(home, monkeypatch)
    monkeypatch.setattr(gitclaim, "worker_working_on", lambda *a, **k: "")
    monkeypatch.setattr(gitclaim, "live_seat_nicks", lambda h: {NICK})
    monkeypatch.setattr(gitclaim, "free_seat_nicks", lambda h, live: {NICK})
    monkeypatch.setattr(gitclaim, "seat_open_job", lambda *a, **k: "")
    draft = dict(PR_6828)
    draft["draft"] = True
    draft["number"] = 71180
    st, why = gitclaim.assign_row(
        home,
        NICK,
        REPO,
        "MRB",
        "71180",
        fetch_issue=lambda r, n: draft,
        pr_exists=lambda r, n: True,
    )
    assert st == "refused"
    assert "draft" in str(why).lower()
    assert "not an open offerable" not in str(why).lower()


def test_fr7118_resync_queues_6797_and_6828(tmp_path: Path):
    home = _home(tmp_path)
    open_prs = [_pr_list_blob(PR_6828), _pr_list_blob(PR_6797)]
    details = {6828: open_prs[0], 6797: open_prs[1]}

    def fetch_json(url: str):
        u = str(url or "")
        for n, det in details.items():
            if f"/pulls/{n}" in u and "/pulls?" not in u:
                return det
        if "/pulls" in u and "state=closed" not in u:
            return list(open_prs)
        if "/issues" in u:
            return []
        return []

    gitclaim.resync_from_github(home, [REPO], fetch_json=fetch_json)
    q = gitclaim.load_queue(home)
    rows = list(q.get("unaccepted") or [])
    ids = {str(r.get("id") or "") for r in rows if str(r.get("task") or "").upper() == "MRB"}
    assert "#6828" in ids, rows
    assert "#6797" in ids, rows
    for row in rows:
        if str(row.get("id")) in ("#6828", "#6797"):
            assert gitclaim.mrb_row_offerable(row) is True
