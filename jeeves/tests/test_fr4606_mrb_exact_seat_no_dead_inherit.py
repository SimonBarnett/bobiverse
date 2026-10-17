"""FR #4606: MRB exact-seat only — recycled sole seat may review; UAT still inherits."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import registered_machines


REPO = "SimonBarnett/bobiverse"
PR = "#4606"
DEAD_AUTHOR = "flamingo-11111"
RECYCLED = "flamingo-99999"
OTHER = "marchhare-12524"
URL = f"https://github.com/{REPO}/pull/4606"


def test_gitclaim_source_skips_dead_inherit_for_mrb_only():
    text = Path(gitclaim.__file__).read_text(encoding="utf-8")
    assert "FR #2604 / #4606" in text or "FR #4606" in text
    # MRB branch continues before nick_inherits_dead_seat; UAT still calls it.
    assert "if task == \"MRB\":" in text
    assert "nick_inherits_dead_seat" in text


def test_recycled_sole_seat_not_blocked_for_mrb(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"flamingo", "marchhare"})
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": RECYCLED, "state": "idle"},
    ]
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [
        {"nick": OTHER, "state": "idle"},
    ]
    bobreport.save_digest(home, digest)

    row = {
        "repo": REPO,
        "task": "MRB",
        "id": PR,
        "seq": 1,
        "ts": "t",
        "line": "x",
        "url": URL,
        "author_seat": DEAD_AUTHOR,
        "event": "pull_request",
        "action": "opened",
    }
    live = {RECYCLED, OTHER}
    assert gitclaim.nick_inherits_dead_seat(RECYCLED, DEAD_AUTHOR, live) is True
    assert gitclaim.review_blocked_for_author(row, RECYCLED, live) is False
    assert gitclaim.review_blocked_for_author(row, DEAD_AUTHOR, live | {DEAD_AUTHOR}) is True

    doc = {"v": 1, "unaccepted": [row], "accepted": [], "done": []}
    gitclaim._write_queue(gitclaim.queue_path(home), doc)
    st, job = gitclaim.offer_focus_top(home, RECYCLED, "#flamingo")
    assert st == "ok"
    assert job is not None and str(job.get("id") or "") == PR


def test_recycled_sole_seat_still_blocked_for_uat(tmp_path, monkeypatch):
    """UAT keeps dead-author inherit (FR #4336); MRB change must not leak."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": RECYCLED, "state": "idle"},
    ]
    bobreport.save_digest(home, digest)

    row = {
        "repo": REPO,
        "task": "UAT",
        "id": REPO,
        "seq": 1,
        "ts": "t",
        "line": "x",
        "author_seat": DEAD_AUTHOR,
    }
    live = {RECYCLED}
    assert gitclaim.nick_inherits_dead_seat(RECYCLED, DEAD_AUTHOR, live) is True
    assert gitclaim.review_blocked_for_author(row, RECYCLED, live) is True
