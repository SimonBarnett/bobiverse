"""FR #8137: DONE MRB PASS is not finished until MERGED; conflict → waiting rebase."""
from __future__ import annotations

import json
from pathlib import Path

import bobreport
import gitclaim
import mrb_merge_on_green
import shop_listen

PASS_SHA = "b" * 40
REPO = "SimonBarnett/toray"
PR = "4"
NICK = "flamingo-6064"
MID = "flamingo"


def _roster(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "registered-machines.json").write_text(
        json.dumps({"v": 1, "machines": [MID]}),
        encoding="utf-8",
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None


def _digest_doing(home: Path) -> None:
    doc = bobreport.empty_digest()
    doc["machines"][MID] = {
        "id": MID,
        "online": True,
        "working_on": f"toray MRB #{PR}",
        "worker_list": [
            {
                "nick": NICK,
                "state": "doing",
                "work": f"toray MRB #{PR}",
                "updated": "2026-11-17T21:10:00Z",
            }
        ],
        "workers": {
            "6064": {
                "pid": "6064",
                "nick": NICK,
                "state": "doing",
                "working_on": f"toray MRB #{PR}",
            }
        },
    }
    bobreport.save_digest(home, doc)


def _queue_accepted(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    gitclaim.queue_path(home).write_text(
        json.dumps(
            {
                "unaccepted": [],
                "accepted": [
                    {
                        "repo": REPO,
                        "task": "MRB",
                        "id": f"#{PR}",
                        "nick": NICK,
                        "accepted_ts": "2026-11-17T21:00:00Z",
                        "url": f"https://github.com/{REPO}/pull/{PR}",
                        "line": f"MRB {REPO}#{PR}",
                    }
                ],
                "done": [],
            }
        ),
        encoding="utf-8",
    )


def test_fr8137_pass_conflicting_waiting_rebase_not_mrb_done(tmp_path, monkeypatch):
    home = tmp_path / "digest"
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    _roster(home)
    _digest_doing(home)
    _queue_accepted(home)

    def fetch_pr(repo, pr, **_k):
        return {
            "sha": PASS_SHA,
            "labels": [],
            "title": "tip",
            "body": "",
            "html_url": f"https://github.com/{REPO}/pull/{PR}",
            "mergeable": "CONFLICTING",
            "merge_state_status": "DIRTY",
            "merged": False,
            "closed": False,
            "checks": "success",
        }

    real_enq = mrb_merge_on_green.enqueue_from_done

    def _enq(home, **kwargs):
        kwargs["fetch_pr"] = fetch_pr
        kwargs["fetch_comments"] = lambda *_a, **_k: []
        return real_enq(home, **kwargs)

    monkeypatch.setattr(mrb_merge_on_green, "enqueue_from_done", _enq)

    result = shop_listen.handle_shop_worker_line(
        home,
        nick=NICK,
        channel=f"#{MID}",
        body=(
            f"DONE MRB {REPO}#{PR} PASS "
            f"https://github.com/{REPO}/pull/{PR}"
        ),
        post_fn=lambda _p: 204,
    )
    assert result.get("handled")
    assert result.get("mrb_pass_phase") == "waiting_rebase"
    assert not gitclaim.mrb_ledger_done_hold(home, REPO, f"#{PR}")
    d2 = bobreport.load_digest(home)
    wl = ((d2.get("machines") or {}).get(MID) or {}).get("worker_list") or []
    assert wl, "worker_list should still exist"
    assert wl[0].get("state") == "waiting"
    assert "waiting rebase" in str(wl[0].get("work") or "").lower()
    q = gitclaim.load_queue(home)
    fixes = [
        r
        for r in (q.get("unaccepted") or [])
        if isinstance(r, dict)
        and str(r.get("task") or "").upper() == "FIX"
        and str(r.get("id") or "").lstrip("#") == PR
    ]
    assert fixes, "expected conflict FIX"
    assert NICK in str(fixes[0].get("giveup_seats") or "")
    done_rows = [
        r
        for r in (q.get("done") or [])
        if isinstance(r, dict) and str(r.get("task") or "").upper() == "MRB"
    ]
    assert done_rows and done_rows[0].get("awaiting") == "waiting_rebase"
    assert done_rows[0].get("pass_sha") == PASS_SHA


def test_fr8137_pass_clean_waiting_merge_then_stamp_on_merged(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    _roster(home)
    _digest_doing(home)
    _queue_accepted(home)

    def fetch_pr(repo, pr, **_k):
        return {
            "sha": PASS_SHA,
            "labels": [],
            "title": "tip",
            "body": "",
            "html_url": f"https://github.com/{REPO}/pull/{PR}",
            "mergeable": "MERGEABLE",
            "merge_state_status": "CLEAN",
            "merged": False,
            "closed": False,
            "checks": "success",
        }

    real_enq = mrb_merge_on_green.enqueue_from_done

    def _enq(home, **kwargs):
        kwargs["fetch_pr"] = fetch_pr
        kwargs["fetch_comments"] = lambda *_a, **_k: []
        return real_enq(home, **kwargs)

    monkeypatch.setattr(mrb_merge_on_green, "enqueue_from_done", _enq)
    result = shop_listen.handle_shop_worker_line(
        home,
        nick=NICK,
        channel=f"#{MID}",
        body=f"DONE MRB {REPO}#{PR} PASS https://github.com/{REPO}/pull/{PR}",
        post_fn=lambda _p: 204,
    )
    assert result.get("mrb_pass_phase") == "waiting_merge"
    assert not gitclaim.mrb_ledger_done_hold(home, REPO, f"#{PR}")
    pending = mrb_merge_on_green.load_ledger(home).get("pending") or []
    assert any(str(p.get("pr") or "") == PR for p in pending if isinstance(p, dict))

    # Merge lands → process_pending stamps mrb_done.
    def fetch_merged(repo, pr, **_k):
        return {
            "sha": PASS_SHA,
            "merged": True,
            "closed": True,
            "checks": "success",
            "html_url": f"https://github.com/{REPO}/pull/{PR}",
        }

    summary = mrb_merge_on_green.process_pending(
        home,
        fetch_pr=fetch_merged,
        fetch_comments=lambda *_a, **_k: [
            {"body": f"MRB PASS @ {PASS_SHA}", "user": {"login": "x"}}
        ],
        merge_fn=lambda *_a, **_k: {"merged": True},
        log=lambda _m: None,
    )
    assert summary.get("dropped", 0) >= 1 or summary.get("merged", 0) >= 1
    assert gitclaim.mrb_ledger_done_hold(home, REPO, f"#{PR}")


def test_fr8137_pass_pending_checks_stays_pending(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    row = mrb_merge_on_green.enqueue_from_done(
        home,
        repo=REPO,
        pr_url=f"https://github.com/{REPO}/pull/{PR}",
        result="PASS",
        nick=NICK,
        fetch_pr=lambda *_a, **_k: {
            "sha": PASS_SHA,
            "labels": [],
            "title": "tip",
            "body": "",
            "html_url": f"https://github.com/{REPO}/pull/{PR}",
            "mergeable": "MERGEABLE",
            "merge_state_status": "UNSTABLE",
            "merged": False,
            "closed": False,
            "checks": "pending",
        },
        fetch_comments=lambda *_a, **_k: [],
    )
    assert row is not None
    assert row.get("phase") == "pending_checks"
    assert str(row.get("status") or "") in ("pending", "skip_hold")


def test_fr8137_enqueue_from_done_idempotent_conflict(tmp_path):
    home = tmp_path / "home"
    home.mkdir()

    def fetch_pr(*_a, **_k):
        return {
            "sha": PASS_SHA,
            "labels": [],
            "title": "tip",
            "body": "",
            "html_url": f"https://github.com/{REPO}/pull/{PR}",
            "mergeable": "CONFLICTING",
            "merge_state_status": "DIRTY",
            "merged": False,
            "closed": False,
            "checks": "success",
        }

    first = mrb_merge_on_green.enqueue_from_done(
        home,
        repo=REPO,
        pr_url=f"https://github.com/{REPO}/pull/{PR}",
        result="PASS",
        nick=NICK,
        fetch_pr=fetch_pr,
        fetch_comments=lambda *_a, **_k: [],
    )
    second = mrb_merge_on_green.enqueue_from_done(
        home,
        repo=REPO,
        pr_url=f"https://github.com/{REPO}/pull/{PR}",
        result="PASS",
        nick=NICK,
        fetch_pr=fetch_pr,
        fetch_comments=lambda *_a, **_k: [],
    )
    assert first and second
    assert first.get("status") == "conflict"
    assert second.get("conflict_fix") in ("duplicate", "added", "reoffer")
    q = gitclaim.load_queue(home)
    fixes = [
        r
        for r in (q.get("unaccepted") or [])
        if isinstance(r, dict) and str(r.get("task") or "").upper() == "FIX"
    ]
    assert len(fixes) == 1
