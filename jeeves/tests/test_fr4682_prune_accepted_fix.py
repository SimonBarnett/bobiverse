"""FR #4682: merged/closed PR must finish accepted FIX (seat stuck NAK busy)."""
from __future__ import annotations

from pathlib import Path

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines

REPO = "SimonBarnett/a-search"


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


def _seed(home: Path) -> None:
    registered_machines.save_registered(home, {"marchhare", "flamingo"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    for mid in ("marchhare", "flamingo"):
        digest["machines"][mid] = bobreport._empty_machine(mid)
        digest["machines"][mid]["workers"] = {
            "1": {
                "state": "doing",
                "nick": f"{mid}-1",
                "working_on": f"FIX {REPO}#3871",
            }
        }
    bobreport.save_digest(home, digest)
    fi.handle_focus_cmd(home, "hi a-search")


def test_merged_webhook_finishes_accepted_fix_and_idles_seat(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _seed(tmp_path)
    _queue(
        tmp_path,
        unaccepted=[
            {
                "repo": REPO,
                "task": "FIX",
                "id": "#3871",
                "seq": 1,
                "ts": "t",
                "line": "x",
                "url": f"https://github.com/{REPO}/pull/3871",
            }
        ],
        accepted=[
            {
                "repo": REPO,
                "task": "FIX",
                "id": "#3871",
                "nick": "flamingo-1",
                "url": f"https://github.com/{REPO}/pull/3871",
            },
            {
                "repo": REPO,
                "task": "MRB",
                "id": "#9999",
                "nick": "marchhare-1",
                "url": f"https://github.com/{REPO}/pull/9999",
            },
        ],
    )
    claim = gitclaim.GitClaim(
        repo=REPO,
        task="MRB",
        id="#3871",
        event="pull_request",
        action="closed",
        line="closed",
        merged=True,
        title="fix(ci): contactVerified stubs",
    )
    assert gitclaim.apply_queue_event(tmp_path, claim) in ("updated", "removed")
    doc = gitclaim.load_queue(tmp_path)
    assert not any(
        str(r.get("task") or "").upper() == "FIX" and str(r.get("id")) == "#3871"
        for r in (doc.get("unaccepted") or [])
    )
    assert not any(
        str(r.get("task") or "").upper() == "FIX" and str(r.get("id")) == "#3871"
        for r in (doc.get("accepted") or [])
    )
    assert any(
        str(r.get("task") or "").upper() == "FIX"
        and str(r.get("id")) == "#3871"
        and str(r.get("result") or "") == "MERGED"
        for r in (doc.get("done") or [])
    )
    # Other ACC rows untouched.
    assert any(
        str(r.get("id")) == "#9999" for r in (doc.get("accepted") or [])
    )
    dig = bobreport.load_digest(tmp_path)
    worker = dig["machines"]["flamingo"]["workers"]["1"]
    assert worker.get("state") == "idle"
    assert not worker.get("working_on")


def test_closed_unmerged_webhook_finishes_accepted_fix(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _seed(tmp_path)
    _queue(
        tmp_path,
        accepted=[
            {
                "repo": REPO,
                "task": "FIX",
                "id": "#3354",
                "nick": "flamingo-1",
                "url": f"https://github.com/{REPO}/pull/3354",
            }
        ],
    )
    claim = gitclaim.GitClaim(
        repo=REPO,
        task="MRB",
        id="#3354",
        event="pull_request",
        action="closed",
        line="closed",
        merged=False,
        title="fix(ci): abandoned",
    )
    assert gitclaim.apply_queue_event(tmp_path, claim) in ("updated", "removed")
    doc = gitclaim.load_queue(tmp_path)
    assert not any(str(r.get("id")) == "#3354" for r in (doc.get("accepted") or []))
    assert any(
        str(r.get("id")) == "#3354" and str(r.get("result") or "") == "CLOSED"
        for r in (doc.get("done") or [])
    )


def test_purge_dead_fix_queue_finishes_accepted_when_pull_gone(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _seed(tmp_path)
    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": REPO,
                "task": "FIX",
                "id": "#3871",
                "url": f"https://github.com/{REPO}/pull/3871",
            },
            {
                "repo": REPO,
                "task": "FIX",
                "id": "#4000",
                "url": f"https://github.com/{REPO}/pull/4000",
            },
        ],
        "accepted": [
            {
                "repo": REPO,
                "task": "FIX",
                "id": "#3871",
                "nick": "flamingo-1",
                "url": f"https://github.com/{REPO}/pull/3871",
            }
        ],
        "done": [],
    }
    n = gitclaim._purge_dead_fix_queue(
        doc,
        open_pulls={REPO: {"#4000"}},
        fetched_repos={REPO},
        home=tmp_path,
    )
    assert n >= 2
    assert not any(str(r.get("id")) == "#3871" for r in (doc.get("unaccepted") or []))
    assert any(str(r.get("id")) == "#4000" for r in (doc.get("unaccepted") or []))
    assert not any(str(r.get("id")) == "#3871" for r in (doc.get("accepted") or []))
    assert any(
        str(r.get("id")) == "#3871" and str(r.get("result") or "") == "MERGED"
        for r in (doc.get("done") or [])
    )


def test_purge_dead_mrb_accepted_finishes_fix_when_pr_gone(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _seed(tmp_path)
    doc = {
        "v": 1,
        "unaccepted": [],
        "accepted": [
            {
                "repo": REPO,
                "task": "FIX",
                "id": "#3871",
                "nick": "flamingo-1",
                "url": f"https://github.com/{REPO}/pull/3871",
            }
        ],
        "done": [],
    }
    n = gitclaim._purge_dead_mrb_accepted(
        doc, pr_exists=lambda r, num: False, home=tmp_path
    )
    assert n == 1
    assert doc["accepted"] == []
    assert any(
        str(r.get("task") or "").upper() == "FIX" and str(r.get("result") or "") == "MERGED"
        for r in doc["done"]
    )
