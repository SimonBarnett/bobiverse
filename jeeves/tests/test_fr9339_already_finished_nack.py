# -*- coding: utf-8 -*-
"""FR #9339: already-finished NACK without current-head verdict must not needs_human."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import registered_machines
import shop_listen
import pytest

REPO = "SimonBarnett/bobiverse"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo", "redqueen"})
    digest = bobreport.empty_digest()
    bobreport.save_digest(tmp_path, digest)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return tmp_path


def _mrb_row(num: int, *, head: str = "", nick: str = "redqueen-6148") -> dict:
    r = {
        "repo": REPO,
        "task": "MRB",
        "id": f"#{num}",
        "line": f"MRB {REPO}#{num}",
        "url": f"https://github.com/{REPO}/pull/{num}",
        "title": f"PR {num}",
        "state": "open",
        "nick": nick,
        "accepted_ts": "2026-11-23T09:00:00Z",
    }
    if head:
        r["head_sha"] = head
    return r


def test_fr9339_is_already_finished_nack_reason():
    assert gitclaim.is_already_finished_nack_reason("already finished")
    assert gitclaim.is_already_finished_nack_reason("already-finished")
    assert gitclaim.is_already_finished_nack_reason("Already Finished (prior DONE)")
    assert not gitclaim.is_already_finished_nack_reason("busy")
    assert not gitclaim.is_already_finished_nack_reason("cannot review")


def test_fr9339_verdict_covers_matching_head():
    row = _mrb_row(9287, head="cbbf6d8eabcdef0123456789abcdef012345678")
    doc = {
        "done": [
            {
                "repo": REPO,
                "task": "MRB",
                "id": "#9287",
                "result": "FAIL",
                "head_sha": "cbbf6d8eabcdef0123456789abcdef012345678",
            }
        ]
    }
    assert gitclaim.mrb_verdict_covers_current_head(row, doc) is True


def test_fr9339_verdict_does_not_cover_new_head_after_fail():
    """S1(a): FAIL on old head must not cover FIX tip head."""
    row = _mrb_row(9287, head="cbbf6d8eabcdef0123456789abcdef012345678")
    doc = {
        "done": [
            {
                "repo": REPO,
                "task": "MRB",
                "id": "#9287",
                "result": "FAIL",
                "head_sha": "eb8ed8b0aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            }
        ]
    }
    assert gitclaim.mrb_verdict_covers_current_head(row, doc) is False


def test_fr9339_no_board_not_covered(home: Path):
    """S1(b): no board / no matching done SHA → not terminal."""
    row = _mrb_row(9308, head="741db4e4bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
    assert gitclaim.mrb_verdict_covers_current_head(row, {"done": []}, home=home) is False
    assert gitclaim.mrb_verdict_covers_current_head(row, None, home=home) is False


def test_fr9339_nack_already_finished_without_verdict_no_needs_human(home: Path):
    """Chair: already finished without current-head verdict → re-queue, no needs_human."""
    row = _mrb_row(9308, head="741db4e4bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [row], "done": [], "workers": {}},
    )
    status, out = shop_listen.return_job_to_unaccepted(
        home,
        repo=REPO,
        task="MRB",
        ident="#9308",
        expected_nick="redqueen-6148",
        reason="already finished",
    )
    assert status == "ok"
    assert out is not None
    assert not out.get("needs_human")
    assert int(out.get("giveup_count") or 0) == 0
    assert not str(out.get("cooldown_until") or "").strip()
    # Seat excluded so next eligible can take it.
    seats = str(out.get("giveup_seats") or "").lower()
    assert "redqueen-6148" in seats


def test_fr9339_nack_already_finished_with_matching_verdict_can_burn(home: Path):
    """S1(c): verdict on current head → already finished is terminal (burns count)."""
    head = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    row = _mrb_row(9159, head=head)
    done = {
        "repo": REPO,
        "task": "MRB",
        "id": "#9159",
        "result": "PASS",
        "head_sha": head,
        "done_ts": "2026-11-23T08:00:00Z",
    }
    # Put PASS in done[] but keep accepted twin so return path is not already-done.
    # Actually if done has the row, return_job hits already-done first. Use matching
    # sha via mrb_verdict only by putting done without accepting already-done path:
    # already-done triggers when di is not None. So for burn path, leave done empty
    # but make mrb_verdict_covers return True via monkeypatch.
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [row], "done": [], "workers": {}},
    )

    import shop_listen as sl

    real = gitclaim.mrb_verdict_covers_current_head

    def _covered(r, doc=None, *, home=None):
        return True

    gitclaim.mrb_verdict_covers_current_head = _covered  # type: ignore
    try:
        status, out = sl.return_job_to_unaccepted(
            home,
            repo=REPO,
            task="MRB",
            ident="#9159",
            expected_nick="redqueen-6148",
            reason="already finished",
        )
    finally:
        gitclaim.mrb_verdict_covers_current_head = real  # type: ignore
    assert status == "ok"
    assert out is not None
    assert int(out.get("giveup_count") or 0) == 1
