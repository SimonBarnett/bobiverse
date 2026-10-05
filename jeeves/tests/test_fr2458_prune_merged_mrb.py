"""FR #2458: prune merged/closed MRB from unaccepted (resync + report surface-heal)."""
from __future__ import annotations

from pathlib import Path
from unittest import mock

import bobreport
import gitclaim


REPO = "SimonBarnett/bobiverse"


def _queue(home: Path, *, unaccepted=None, accepted=None, done=None):
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": list(unaccepted or []),
            "accepted": list(accepted or []),
            "done": list(done or []),
        },
    )


def _mrb(num=2455, **extra):
    row = {
        "repo": REPO,
        "task": "MRB",
        "id": f"#{num}",
        "seq": 1,
        "ts": "t",
        "line": "x",
        "url": f"https://github.com/{REPO}/pull/{num}",
    }
    row.update(extra)
    return row


def test_norm_row_id_and_same_match_hashless():
    assert gitclaim._norm_row_id("2455") == "#2455"
    assert gitclaim._norm_row_id("#2455") == "#2455"
    row = _mrb(2455, id="2455")
    assert gitclaim._same(row, REPO, "MRB", "#2455")
    assert gitclaim._same(row, REPO, "mrb", "2455")


def test_webhook_closed_merged_removes_hashless_id(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _queue(tmp_path, unaccepted=[_mrb(2455, id="2455")])
    claim = gitclaim.GitClaim(
        repo=REPO,
        task="MRB",
        id="#2455",
        event="pull_request",
        action="closed",
        line="",
        merged=True,
    )
    assert gitclaim.apply_queue_event(tmp_path, claim) in ("updated", "removed")
    doc = gitclaim._load_queue_unlocked(tmp_path)
    assert not any(
        str(r.get("task") or "").upper() == "MRB" and gitclaim._norm_row_id(r.get("id")) == "#2455"
        for r in (doc.get("unaccepted") or [])
    )


def test_purge_open_pulls_drops_merged_for_fetched_repo():
    doc = {"v": 1, "unaccepted": [_mrb(2455), _mrb(99)], "accepted": [], "done": []}
    n = gitclaim._purge_dead_mrb_unaccepted(
        doc,
        open_pulls={REPO: {"#99"}},
        fetched_repos={REPO},
    )
    assert n == 1
    ids = {gitclaim._norm_row_id(r.get("id")) for r in doc["unaccepted"]}
    assert ids == {"#99"}


def test_purge_open_pulls_keeps_when_repo_not_fetched():
    doc = {"v": 1, "unaccepted": [_mrb(2455)], "accepted": [], "done": []}
    n = gitclaim._purge_dead_mrb_unaccepted(
        doc,
        open_pulls={REPO: set()},
        fetched_repos=set(),  # fetch failed — must not wipe
    )
    assert n == 0
    assert len(doc["unaccepted"]) == 1


def test_resync_drops_merged_mrb_absent_from_open_pulls(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _queue(
        tmp_path,
        unaccepted=[
            _mrb(2455, offered_to="marchhare-1"),
            _mrb(99),
        ],
    )

    def fetch(url: str):
        if "/pulls?" in url and "state=open" in url:
            return [{"number": 99, "title": "open", "body": ""}]
        if "/issues?" in url:
            return []
        if "/pulls?" in url and "state=closed" in url:
            return []
        raise AssertionError(url)

    stats = gitclaim.resync_from_github(tmp_path, [REPO], fetch_json=fetch)
    assert "ok" in stats or "fetched" in stats or isinstance(stats, dict)
    doc = gitclaim._load_queue_unlocked(tmp_path)
    ids = {gitclaim._norm_row_id(r.get("id")) for r in (doc.get("unaccepted") or []) if str(r.get("task") or "").upper() == "MRB"}
    assert "#2455" not in ids
    assert "#99" in ids


def test_public_queue_purges_via_pr_exists(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _queue(tmp_path, unaccepted=[_mrb(2455), _mrb(99)])

    def fake_checker(home=None, cache=None):
        return lambda repo, num: str(num).lstrip("#") == "99"

    monkeypatch.setattr(gitclaim, "github_pr_exists_checker", fake_checker)
    q = bobreport._public_queue(tmp_path)
    ids = {gitclaim._norm_row_id(r.get("id")) for r in q["unaccepted"]}
    assert "#2455" not in ids
    assert "#99" in ids
