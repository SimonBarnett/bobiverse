"""Jeeves MUST hand out work (Simon 2026-10-04): short empty reply, per-repo focus filters, no NAK while focused work exists."""
from __future__ import annotations

import pytest

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("JEEVES_OWNER_ACCOUNT", "simon")
    for k in ("JEEVES_FOCUS_MUTATORS", "JEEVES_FOCUS_MUTATOR_ACCOUNTS"):
        monkeypatch.delenv(k, raising=False)
    registered_machines.save_registered(tmp_path, {"ionos", "win-mpre8vi4u6u"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def _row(repo, task, num, seq, **kw):
    r = {"repo": repo, "task": task, "id": f"#{num}", "seq": seq,
         "ts": f"2026-10-01T10:00:{seq:02d}Z", "line": "x"}
    r.update(kw)
    return r


def _queue(home, rows):
    gitclaim._write_queue(gitclaim.queue_path(home), {"v": 1, "unaccepted": rows, "accepted": []})


def test_empty_reply_is_one_short_line_even_with_stats():
    stats = {"unaccepted": 36, "out_of_focus": 36, "require_machine": 2, "strict": True}
    line = gitclaim.format_nothing_queued("ionos-1", stats)
    assert line == "ionos-1: nothing queued"
    assert "\n" not in line and "offerable" not in line


def test_empty_detail_for_log_keeps_breakdown():
    detail = gitclaim.format_empty_offer_detail("ionos-1", {"unaccepted": 3, "out_of_focus": 3})
    assert detail and "ionos-1" in detail


def test_focused_repo_row_offered_immediately(_home):
    _queue(_home, [_row("SimonBarnett/bobiverse", "FR", 10, 1), _row("SimonBarnett/other", "FR", 11, 2)])
    fi.handle_focus_cmd(_home, "bobiverse")
    status, job = gitclaim.offer_focus_top(_home, "ionos-1", "#ionos")
    assert status != "empty" and job and job["repo"].endswith("bobiverse")


def test_falls_through_to_next_focused_repo_when_first_has_no_rows(_home):
    _queue(_home, [_row("SimonBarnett/xai-cookbook", "FR", 5, 1)])
    fi.handle_focus_cmd(_home, "high bobiverse")
    fi.handle_focus_cmd(_home, "medium xai-cookbook")
    status, job = gitclaim.offer_focus_top(_home, "ionos-1", "#ionos")
    assert status != "empty" and job["repo"].endswith("xai-cookbook")


@pytest.mark.parametrize("tok,expect", [("hi", 1), ("lo", 9), ("high", 1), ("low", 9), ("medium", 5), ("3", 3)])
def test_repo_then_priority_filter_order(_home, tok, expect):
    fi.handle_focus_cmd(_home, f"bobiverse {tok}")
    meta = fi.load_focus(_home)["repos"]
    (name, m), = list(meta.items())
    assert "bobiverse" in name and int(m["priority"]) == expect


def test_priority_then_repo_order_still_works(_home):
    fi.handle_focus_cmd(_home, "lo bobiverse")
    (name, m), = list(fi.load_focus(_home)["repos"].items())
    assert int(m["priority"]) == 9


def test_hi_repo_outranks_lo_repo(_home):
    _queue(_home, [_row("SimonBarnett/aaa", "FR", 1, 1), _row("SimonBarnett/bobiverse", "FR", 2, 2)])
    fi.handle_focus_cmd(_home, "aaa lo")
    fi.handle_focus_cmd(_home, "bobiverse hi")
    status, job = gitclaim.offer_focus_top(_home, "ionos-1", "#ionos")
    assert job["repo"].endswith("bobiverse")



def test_pinned_mrb_not_stranded_when_only_other_machine_seats_are_pinned_out(_home):
    """MRB #2319 class: pin=ionos, author ionos seat A, sibling ionos seat B must get it even
    though a marchhare seat is live (marchhare is forbidden by the pin, so it is not viable)."""
    registered_machines.save_registered(_home, {"ionos", "win-mpre8vi4u6u", "marchhare"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    row = _row("SimonBarnett/bobiverse", "MRB", 2319, 1, require_machine="ionos",
               author_seat="win-mpre8vi4u6u-14452", implementer_seat="win-mpre8vi4u6u-14452",
               url="https://github.com/SimonBarnett/bobiverse/pull/2319")
    _queue(_home, [row])
    live = {"win-mpre8vi4u6u-14452", "win-mpre8vi4u6u-7764", "marchhare-35016"}
    assert gitclaim.review_blocked_for_author(row, "win-mpre8vi4u6u-7764", live) is False
    assert gitclaim.review_blocked_for_author(row, "win-mpre8vi4u6u-14452", live) is True  # no self-MRB


def test_unpinned_mrb_sibling_still_deferred_to_other_machine(_home):
    registered_machines.save_registered(_home, {"win-mpre8vi4u6u", "marchhare"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    row = _row("SimonBarnett/bobiverse", "MRB", 5, 1, author_seat="win-mpre8vi4u6u-14452")
    live = {"win-mpre8vi4u6u-14452", "win-mpre8vi4u6u-7764", "marchhare-35016"}
    assert gitclaim.review_blocked_for_author(row, "win-mpre8vi4u6u-7764", live) is True


def test_closed_issue_row_is_never_offered(_home):
    _queue(_home, [_row("SimonBarnett/bobiverse", "FR", 2218, 1), _row("SimonBarnett/bobiverse", "FR", 2400, 2)])
    closed = lambda repo, num: num == "2218"  # noqa: E731
    status, job = gitclaim.offer_focus_top(_home, "ionos-1", "#ionos", issue_closed=closed)
    assert status == "ok" and job["id"] == "#2400"


def test_issue_closed_hook_error_does_not_block_offer(_home):
    _queue(_home, [_row("SimonBarnett/bobiverse", "FR", 7, 1)])

    def boom(repo, num):
        raise RuntimeError("network")

    status, job = gitclaim.offer_focus_top(_home, "ionos-1", "#ionos", issue_closed=boom)
    assert status == "ok" and job["id"] == "#7"
