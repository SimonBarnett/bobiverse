"""MRB #8191 / FR #9885: PASS seat blocked; second seat may take merge-wait MRB."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import registered_machines
import shop_listen

REPO = "SimonBarnett/Club-Madeira"


def _digest(home: Path) -> None:
    registered_machines.save_registered(home, {"marchhare", "flamingo"})
    digest = bobreport.empty_digest()
    for mid, wid in (("marchhare", "41928"), ("flamingo", "9")):
        digest["machines"][mid] = bobreport._empty_machine(mid)
        digest["machines"][mid]["workers"] = {wid: {"state": "idle"}}
    bobreport.save_digest(home, digest)


def _mrb(num=10, **extra):
    row = {
        "repo": REPO,
        "task": "MRB",
        "id": f"#{num}",
        "seq": 1,
        "ts": "t",
        "line": f"MRB {REPO}#{num}",
        "url": f"https://github.com/{REPO}/pull/{num}",
    }
    row.update(extra)
    return row


def test_mrb8191_done_hold_blocks_second_seat_after_restore(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [_mrb(10, nick="marchhare-41928")], "done": []},
    )
    st, job = shop_listen.complete_job_by_ref(
        tmp_path,
        nick="marchhare-41928",
        repo=REPO,
        task="MRB",
        ident="#10",
        result="PASS",
        url=f"https://github.com/{REPO}/pull/10",
    )
    assert st == "ok"
    assert job.get("result") == "PASS"
    key = gitclaim._lkey(REPO, "#10")
    assert key not in (gitclaim.ledger_load(tmp_path).get("mrb_done") or {})
    done_rows = list(gitclaim._load_queue_unlocked(tmp_path).get("done") or [])
    assert any(str(r.get("id")) == "#10" for r in done_rows)

    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [_mrb(10, mergeable=True, mergeable_state="clean")],
            "accepted": [],
            "done": done_rows,
        },
    )
    assert gitclaim.offer_focus_top(tmp_path, "marchhare-41928", "#marchhare")[0] == "empty"

    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [_mrb(10, mergeable=True, mergeable_state="clean")],
            "accepted": [],
            "done": done_rows,
        },
    )
    def pr_open(repo: str, num: str) -> bool:
        return repo == REPO and str(num).lstrip("#") == "10"

    assert (
        gitclaim.offer_focus_top(tmp_path, "flamingo-9", "#flamingo", pr_exists=pr_open)[0]
        == "ok"
    )
    assert len(gitclaim.load_unaccepted(tmp_path)) == 1
