"""FR #4661: resync must not re-queue PASSed auto-merge MRB; never re-offer to DONE nick."""
from __future__ import annotations

import gitclaim
import mrb_merge_on_green

SHA = "a" * 40
OTHER = "b" * 40
REPO = "SimonBarnett/a-search"
NICK = "flamingo-30252"
OTHER_NICK = "marchhare-13128"


def _pr(n: int, *, sha: str, auto_merge: dict | None):
    return {
        "number": n,
        "title": "fix: x",
        "body": "Closes o/a#50",
        "html_url": f"https://github.com/{REPO}/pull/{n}",
        "state": "open",
        "draft": False,
        "auto_merge": auto_merge,
        "head": {"sha": sha},
        "user": {"login": "u"},
        "checks": "pending",
    }


def _fetch(pr):
    def fetch_json(url: str):
        if "/pulls" in url and "state=closed" not in url:
            return [pr]
        if "/issues" in url:
            return []
        return []

    return fetch_json


def _queue(tmp_path, *, done_pass: bool, unaccepted: bool):
    done = []
    if done_pass:
        done.append(
            {
                "repo": REPO,
                "task": "MRB",
                "id": "#3246",
                "result": "PASS",
                "url": f"https://github.com/{REPO}/pull/3246",
                "done_by": NICK,
                "nick": NICK,
            }
        )
    una = []
    if unaccepted:
        una.append(
            {
                "repo": REPO,
                "task": "MRB",
                "id": "#3246",
                "seq": 1,
                "ts": "t",
                "line": "",
                "url": f"https://github.com/{REPO}/pull/3246",
            }
        )
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": una, "accepted": [], "done": done},
    )


def test_resync_skips_ci_wait_when_done_pass_without_ledger(tmp_path, monkeypatch):
    """Regression #4661: ledger miss must not re-queue when done[] PASS + auto_merge."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _queue(tmp_path, done_pass=True, unaccepted=False)
    # No merge-on-green ledger enqueue — simulates enqueue_from_done race/miss.
    res = gitclaim.resync_from_github(
        tmp_path,
        [REPO],
        fetch_json=_fetch(_pr(3246, sha=SHA, auto_merge={"merge_method": "squash"})),
    )
    assert res.get("ok") is True
    rows = gitclaim.load_unaccepted(tmp_path)
    assert [r for r in rows if r.get("task") == "MRB" and r.get("id") == "#3246"] == []


def test_resync_prunes_queued_row_when_done_pass_auto_merge(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _queue(tmp_path, done_pass=True, unaccepted=True)
    gitclaim.resync_from_github(
        tmp_path,
        [REPO],
        fetch_json=_fetch(_pr(3246, sha=SHA, auto_merge={"merge_method": "squash"})),
    )
    rows = gitclaim.load_unaccepted(tmp_path)
    assert [r for r in rows if r.get("task") == "MRB" and r.get("id") == "#3246"] == []


def test_offer_skips_done_pass_nick_even_if_row_queued(tmp_path, monkeypatch):
    """Never re-offer the PASSed MRB to the seat that DONE'd it (#4661)."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _queue(tmp_path, done_pass=True, unaccepted=True)
    st, _ = gitclaim.offer_focus_top(tmp_path, NICK, "#flamingo")
    assert st == "empty"
    # A different seat may still see it only if not ci-wait; with auto_merge+done
    # resync should have pruned — here row is still queued without resync, so
    # other seats can take a genuine re-review when SHA changed. Same SHA + done
    # PASS: offer gate still blocks the DONE nick only.
    st2, job = gitclaim.offer_focus_top(tmp_path, OTHER_NICK, "#marchhare")
    # Without GitHub, other seat can be offered the phantom row (pre-resync).
    assert st2 in ("ok", "empty")


def test_done_pass_sha_fallback_matches_head(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _queue(tmp_path, done_pass=True, unaccepted=False)
    sha = gitclaim.done_mrb_pass_sha_for_ci_wait(tmp_path, REPO, 3246, SHA)
    assert sha == SHA
    assert gitclaim.done_mrb_pass_sha_for_ci_wait(tmp_path, REPO, 999, SHA) == ""
    assert gitclaim.nick_done_mrb_pass(tmp_path, NICK, REPO, "#3246") is True
    assert gitclaim.nick_done_mrb_pass(tmp_path, OTHER_NICK, REPO, "#3246") is False

def test_duplicate_after_done_hold_prunes_unaccepted(tmp_path, monkeypatch):
    """FR #4661 / #6565: done[] MRB PASS clears hold + prunes without live GitHub."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    # BUILD failure: seat_done_without_later_offer is False (no ledger stamp) and
    # _lost_done_github_result used live a-search#3246. Force GitHub empty/fail.
    monkeypatch.setattr(
        "mrb_merge_gate.fetch_issue_comments",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    _queue(tmp_path, done_pass=True, unaccepted=True)
    assert gitclaim.note_seat_hold(
        tmp_path,
        NICK,
        {"repo": REPO, "task": "MRB", "id": "#3246"},
        via="offer",
    )
    assert gitclaim.seat_done_without_later_offer(
        tmp_path, NICK, REPO, "MRB", "#3246"
    ) is False
    assert gitclaim.nick_done_mrb_pass(tmp_path, NICK, REPO, "#3246") is True
    freed = gitclaim.release_duplicate_done_hold(tmp_path, NICK)
    assert "MRB" in freed
    rows = gitclaim.load_unaccepted(tmp_path)
    assert [r for r in rows if r.get("id") == "#3246"] == []
    assert gitclaim.seat_open_job(tmp_path, NICK) == ""


def test_done_mrb_pass_does_not_clear_fix_hold(tmp_path, monkeypatch):
    """Hostile MRB #6583: earlier MRB PASS must not clear a FIX hold on same pull."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setattr(
        "mrb_merge_gate.fetch_issue_comments",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    _queue(tmp_path, done_pass=True, unaccepted=False)
    # ack-missing keeps the hold without a queue FIX row (FR #4415).
    assert gitclaim.note_seat_hold(
        tmp_path,
        NICK,
        {"repo": REPO, "task": "FIX", "id": "#3246"},
        via="ack-missing",
    )
    assert gitclaim.nick_done_mrb_pass(tmp_path, NICK, REPO, "#3246") is True
    freed = gitclaim.release_duplicate_done_hold(tmp_path, NICK)
    assert freed == ""
    assert "FIX" in gitclaim.seat_open_job(tmp_path, NICK)


def test_done_mrb_pass_keeps_hold_after_later_offer(tmp_path, monkeypatch):
    """Hostile MRB #6583: offered > done keeps hold even when done[] has PASS."""
    import time

    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setattr(
        "mrb_merge_gate.fetch_issue_comments",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    _queue(tmp_path, done_pass=True, unaccepted=True)
    job = {"repo": REPO, "task": "MRB", "id": "#3246"}
    gitclaim.ledger_stamp_seat_job(tmp_path, NICK, job, "done")
    time.sleep(0.02)
    gitclaim.ledger_stamp_seat_job(tmp_path, NICK, job, "offered")
    assert gitclaim.note_seat_hold(tmp_path, NICK, job, via="offer")
    assert gitclaim.seat_done_without_later_offer(
        tmp_path, NICK, REPO, "MRB", "#3246"
    ) is False
    assert gitclaim.nick_done_mrb_pass(tmp_path, NICK, REPO, "#3246") is True
    freed = gitclaim.release_duplicate_done_hold(tmp_path, NICK)
    assert freed == ""
    assert "MRB" in gitclaim.seat_open_job(tmp_path, NICK)
