"""FR #2375: merged / fix(mrb-N) PRs must not be re-offered as MRB (esp. to author)."""
from __future__ import annotations

from pathlib import Path

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines

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


def _seed(home: Path) -> None:
    registered_machines.save_registered(home, {"marchhare", "flamingo"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    for mid in ("marchhare", "flamingo"):
        digest["machines"][mid] = bobreport._empty_machine(mid)
        digest["machines"][mid]["workers"] = {"1": {"state": "idle", "nick": f"{mid}-1"}}
    bobreport.save_digest(home, digest)
    fi.handle_focus_cmd(home, "hi bobiverse")


def test_fr2375_fix_mrb_title_not_offerable():
    row = {
        "repo": REPO,
        "task": "MRB",
        "id": "#2374",
        "url": f"https://github.com/{REPO}/pull/2374",
        "title": "fix(mrb-2371): preserve accepted_by for stale-busy heal",
        "line": "x",
    }
    assert gitclaim.is_mrb_fix_pr_title(row["title"])
    assert gitclaim.mrb_row_offerable(row, pr_exists=None) is False
    assert gitclaim.mrb_row_offerable(row, pr_exists=lambda r, n: True) is False


def test_fr2375_offer_skips_fix_mrb_row(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _seed(tmp_path)
    _queue(
        tmp_path,
        unaccepted=[
            {
                "repo": REPO,
                "task": "MRB",
                "id": "#2374",
                "seq": 1,
                "ts": "t",
                "line": "x",
                "title": "fix(mrb-2371): preserve accepted_by",
                "url": f"https://github.com/{REPO}/pull/2374",
                "author_seat": "marchhare-40208",
            }
        ],
    )
    status, job = gitclaim.offer_focus_top(
        tmp_path, "flamingo-1", "#flamingo", pr_exists=None
    )
    assert status == "empty"
    assert job is None


def test_fr2375_merged_webhook_purges_acc_and_stamps_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _seed(tmp_path)
    _queue(
        tmp_path,
        unaccepted=[
            {
                "repo": REPO,
                "task": "MRB",
                "id": "#2374",
                "seq": 1,
                "ts": "t",
                "line": "x",
                "url": f"https://github.com/{REPO}/pull/2374",
            }
        ],
        accepted=[
            {
                "repo": REPO,
                "task": "MRB",
                "id": "#2374",
                "nick": "marchhare-40208",
                "url": f"https://github.com/{REPO}/pull/2374",
            }
        ],
    )
    claim = gitclaim.GitClaim(
        repo=REPO,
        task="MRB",
        id="#2374",
        event="pull_request",
        action="closed",
        line="closed",
        merged=True,
        title="fix(mrb-2371): preserve accepted_by",
    )
    assert gitclaim.apply_queue_event(tmp_path, claim) in ("updated", "removed")
    doc = gitclaim.load_queue(tmp_path)
    assert not any(
        str(r.get("id")) == "#2374" for r in (doc.get("unaccepted") or [])
    )
    assert not any(
        str(r.get("id")) == "#2374" for r in (doc.get("accepted") or [])
    )
    assert any(
        str(r.get("id")) == "#2374" and str(r.get("result") or "") == "MERGED"
        for r in (doc.get("done") or [])
    )
    assert gitclaim.mrb_ledger_done_hold(tmp_path, REPO, "#2374")
    status, job = gitclaim.offer_focus_top(
        tmp_path, "flamingo-1", "#flamingo", pr_exists=None
    )
    assert status == "empty"
