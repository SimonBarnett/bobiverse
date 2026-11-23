"""FR #9469: GIVEUP blocked:depends-on stamps plain Depends-on: and skips re-offer."""
from __future__ import annotations

from pathlib import Path

import depends_on
import gitclaim
import shop_listen


REPO = "SimonBarnett/bobiverse"


def test_parse_blocked_depends_giveup_refs():
    assert gitclaim.parse_blocked_depends_giveup_refs(
        "blocked:depends-on #9354", home_repo=REPO
    ) == [(REPO, 9354)]
    assert gitclaim.parse_blocked_depends_giveup_refs(
        "GIVEUP reason=blocked-on #8700 still open", home_repo=REPO
    ) == [(REPO, 8700)]
    assert gitclaim.parse_blocked_depends_giveup_refs(
        "depends_unresolved SimonBarnett/other#77", home_repo=REPO
    ) == [("SimonBarnett/other", 77)]
    assert gitclaim.parse_blocked_depends_giveup_refs("out of fuel", home_repo=REPO) == []


def test_merge_depends_on_body_unions_and_plain_line():
    body = "**Depends-on:** #8700\n## What\nwork\n"
    new, changed = depends_on.merge_depends_on_body(
        body, [(REPO, 9354)], repo=REPO
    )
    assert changed
    assert new.startswith("Depends-on: #8700, #9354\n")
    assert "**Depends-on:**" not in new
    assert "## What" in new
    again, changed2 = depends_on.merge_depends_on_body(new, [(REPO, 9354)], repo=REPO)
    assert changed2 is False
    assert again == new


def test_apply_depends_on_giveup_stamp_updates_row_without_github():
    row = {
        "task": "FR",
        "repo": REPO,
        "id": "#8833",
        "body": "Depends-on: #8700\nImplement.\n",
        "labels": [],
    }
    refs = gitclaim.apply_depends_on_giveup_stamp(
        row, "blocked:depends-on #9354", patch_github=False
    )
    assert refs == [(REPO, 9354)]
    assert row["body"].startswith("Depends-on: #8700, #9354")


def test_apply_depends_on_giveup_stamp_patches_github(monkeypatch):
    patched: list[tuple] = []

    class _Filer:
        def edit_issue_body(self, repo, number, body):
            patched.append((repo, number, body))

    row = {
        "task": "FR",
        "repo": REPO,
        "id": "8833",
        "body": "Depends-on: #8700\n",
        "labels": [],
    }
    monkeypatch.setattr(
        gitclaim,
        "fetch_github_issue_dict",
        lambda *_a, **_k: {"body": "Depends-on: #8700\nold\n"},
    )
    refs = gitclaim.apply_depends_on_giveup_stamp(
        row,
        "blocked:depends-on #9354",
        patch_github=True,
        filer=_Filer(),
    )
    assert refs == [(REPO, 9354)]
    assert patched and patched[0][0] == REPO and patched[0][1] == 8833
    assert patched[0][2].startswith("Depends-on: #8700, #9354")
    assert "Depends-on: #8700, #9354" in row["body"]


def test_shop_giveup_stamps_depends_and_offer_skips(tmp_path: Path, monkeypatch):
    home = tmp_path / "chair"
    home.mkdir()
    parent = {
        "task": "FR",
        "repo": REPO,
        "id": "#9354",
        "seq": 1,
        "title": "parent still open",
        "body": "Depends-on: (none)\n",
        "labels": [],
    }
    child = {
        "task": "FR",
        "repo": REPO,
        "id": "#8833",
        "seq": 2,
        "title": "child",
        "body": "Depends-on: #8700\n",
        "labels": [],
        "nick": "redqueen-1",
        "accepted_by": "redqueen-1",
        "accepted_ts": "2026-11-23T20:00:00Z",
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [parent], "accepted": [child], "done": []},
    )

    _orig = gitclaim.apply_depends_on_giveup_stamp

    def _stamp_no_gh(row, reason, **_kw):
        return _orig(row, reason, patch_github=False)

    monkeypatch.setattr(gitclaim, "apply_depends_on_giveup_stamp", _stamp_no_gh)

    status, job = shop_listen.return_job_to_unaccepted(
        home,
        repo=REPO,
        task="FR",
        ident="#8833",
        now=1_700_000_000.0,
        reason="blocked:depends-on #9354",
        expected_nick="redqueen-1",
    )
    assert status == "ok"
    assert job is not None
    assert "Depends-on: #8700, #9354" in str(job.get("body") or "")
    doc = gitclaim.load_queue(home)
    stamped = None
    for row in doc.get("unaccepted") or []:
        if str(row.get("id")) in ("#8833", "8833"):
            stamped = row
            break
    assert stamped is not None
    why = gitclaim.depends_gate_reason(stamped, doc=doc)
    assert why == gitclaim.DEPENDS_OPEN_REASON
