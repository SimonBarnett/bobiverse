"""FR #628 / t849u: repo-level focus admits new pipeline rows, no post-DONE NAK gate, offer-time GIVEUP
filtering (no self-MRB/UAT, no re-offer to a seat that gave up, machine-pinned rows), chair !assign."""
from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("JEEVES_OWNER_ACCOUNT", "simon")
    registered_machines.save_registered(tmp_path, {"ionos", "marchhare"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def _now_iso(delta_s=0):
    return datetime.fromtimestamp(time.time() - delta_s, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row(repo, task, num, seq, age_s=60, **kw):
    r = {"repo": repo, "task": task, "id": f"#{num}", "seq": seq, "ts": _now_iso(age_s), "line": "x",
         "title": f"t{num}"}
    if task == "MRB":
        r["url"] = f"https://github.com/{repo}/pull/{num}"
    r.update(kw)
    return r


def _queue(home, rows):
    gitclaim._write_queue(gitclaim.queue_path(home), {"v": 1, "unaccepted": rows, "accepted": []})


def _ids(home):
    return [(r["task"], r["id"]) for r in gitclaim.ordered_unaccepted(home)]


# ------------------------------------------------------------ gate
def test_no_post_done_nak_gate_by_default(_home, monkeypatch):
    assert gitclaim.IDLE_S == 0.0
    now = time.time()
    gitclaim.note_worker_activity(_home, "ionos-1", now)       # just finished a job
    assert gitclaim.bored_gate(_home, "ionos-1", "#ionos", now + 1) == "ok"


# ------------------------------------------------------------ repo focus admits new rows
def test_repo_focus_admits_new_rows_in_strict_without_item_focus(_home):
    _queue(_home, [_row("o/a", "FR", 1, 1), _row("o/b", "FR", 2, 2)])
    fi.handle_focus_cmd(_home, "strict on")
    fi.handle_focus_cmd(_home, "1 o/a")
    assert _ids(_home) == [("FR", "#1")]
    # a brand-new MRB / UAT / FR arrives for o/a: offerable without any per-number focus
    _queue(_home, [_row("o/a", "FR", 1, 1), _row("o/a", "UAT", 3, 3), _row("o/a", "MRB", 4, 4), _row("o/b", "MRB", 5, 5)])
    assert _ids(_home) == [("MRB", "#4"), ("UAT", "#3"), ("FR", "#1")]


def test_repo_focus_orders_repos_by_priority_then_entry_time(_home):
    _queue(_home, [_row("o/c", "MRB", 1, 1), _row("o/a", "FR", 2, 2), _row("o/b", "FR", 3, 3), _row("o/b", "UAT", 4, 4)])
    fi.handle_focus_cmd(_home, "2 o/b")
    fi.handle_focus_cmd(_home, "1 o/a")
    fi.handle_focus_cmd(_home, "2 o/c")
    assert _ids(_home) == [("FR", "#2"), ("UAT", "#4"), ("FR", "#3"), ("MRB", "#1")]


def test_item_rank_beats_repo_order(_home):
    _queue(_home, [_row("o/a", "MRB", 1, 1), _row("o/b", "FR", 2, 2)])
    fi.handle_focus_cmd(_home, "1 o/a")
    fi.handle_focus_cmd(_home, "1 o/b#2")
    assert _ids(_home)[0] == ("FR", "#2")


def test_stale_uat_and_skip_rows_not_admitted_by_repo_focus(_home):
    _queue(_home, [
        _row("o/a", "UAT", 1, 1, age_s=3 * 86400),                     # old merge history
        _row("o/a", "UAT", 2, 2, age_s=3600),
        _row("o/a", "FR", 3, 3, labels=["mrb-home"]),
        _row("o/a", "FR", 4, 4, labels=["needs-human"]),
        _row("o/a", "FR", 5, 5, needs_human=True),
        _row("o/a", "FR", 6, 6, title="CRITICAL: Jeeves chair DOWN again"),
        _row("o/a", "FR", 7, 7),
    ])
    fi.handle_focus_cmd(_home, "strict on")
    fi.handle_focus_cmd(_home, "1 o/a")
    assert _ids(_home) == [("UAT", "#2"), ("FR", "#7")]


def test_unfocused_repo_stays_hidden_in_strict(_home):
    _queue(_home, [_row("o/a", "FR", 1, 1), _row("o/z", "MRB", 2, 2)])
    fi.handle_focus_cmd(_home, "strict on")
    fi.handle_focus_cmd(_home, "1 o/a")
    assert ("MRB", "#2") not in _ids(_home)


# ------------------------------------------------------------ offer-time filtering
def test_offer_skips_self_mrb_and_gives_next_eligible(_home):
    _queue(_home, [
        _row("o/a", "MRB", 1, 1, author_seat="ionos-11", implementer="ionos-11"),
        _row("o/a", "FR", 2, 2),
    ])
    fi.handle_focus_cmd(_home, "1 o/a")
    st, job = gitclaim.offer_focus_top(_home, "ionos-11", "#ionos")
    assert st == "ok" and (job["task"], job["id"]) == ("FR", "#2")


def test_offer_empty_when_only_self_review_left(_home):
    _queue(_home, [_row("o/a", "UAT", 1, 1, author_seat="ionos-11")])
    fi.handle_focus_cmd(_home, "1 o/a")
    assert gitclaim.offer_focus_top(_home, "ionos-11", "#ionos")[0] == "empty"
    assert gitclaim.offer_focus_top(_home, "ionos-12", "#ionos")[0] == "ok"


def test_never_reoffer_row_to_seat_that_gave_it_up(_home):
    _queue(_home, [_row("o/a", "UAT", 1, 1, giveup_seats="ionos-11"), _row("o/a", "FR", 2, 2)])
    fi.handle_focus_cmd(_home, "1 o/a")
    st, job = gitclaim.offer_focus_top(_home, "ionos-11", "#ionos")
    assert (job["task"], job["id"]) == ("FR", "#2")
    st, job = gitclaim.offer_focus_top(_home, "ionos-12", "#ionos")
    assert (job["task"], job["id"]) == ("UAT", "#1")


def test_machine_pinned_row_not_offered_elsewhere(_home):
    _queue(_home, [_row("o/a", "FR", 1, 1, require_machine="ionos"), _row("o/a", "FR", 2, 2, labels=["machine:ionos"])])
    fi.handle_focus_cmd(_home, "1 o/a")
    assert gitclaim.offer_focus_top(_home, "marchhare-5", "#marchhare")[0] == "empty"
    assert gitclaim.offer_focus_top(_home, "ionos-5", "#ionos")[0] == "ok"


# ------------------------------------------------------------ !assign
def test_parse_assign_cmd():
    assert gitclaim.parse_assign_cmd("!assign marchhare-41928 SimonBarnett/bobiverse mrb 637") == (
        "marchhare-41928", "SimonBarnett/bobiverse", "MRB", "#637")
    assert gitclaim.parse_assign_cmd("!assign a b FR #5") == ("a", "b", "FR", "#5")
    assert gitclaim.parse_assign_cmd("!assign a b XYZ 5") is None
    assert gitclaim.parse_assign_cmd("!assign a b FR") is None


def test_assign_row_ok_then_ack_accepts(_home):
    _queue(_home, [_row("o/a", "MRB", 9, 1)])
    st, job = gitclaim.assign_row(_home, "ionos-7", "o/a", "MRB", "#9")
    assert st == "ok"
    assert gitclaim.format_assign_line("ionos-7", job) == "ionos-7: MRB o/a#9 https://github.com/o/a/pull/9"
    st2, acc = gitclaim.accept_offered(_home, "ionos-7", "#ionos")
    assert st2 == "ok" and acc["id"] == "#9"
    assert gitclaim.assign_row(_home, "ionos-8", "o/a", "MRB", "#9")[0] == "refused"   # already accepted


@pytest.mark.parametrize("nick", ["Jeeves", "bob-ionos", "ionos-"])
def test_assign_row_rejects_non_seat(_home, nick):
    _queue(_home, [_row("o/a", "FR", 1, 1)])
    assert gitclaim.assign_row(_home, nick, "o/a", "FR", "#1")[0] == "refused"


def test_assign_row_refusals(_home, monkeypatch):
    _queue(_home, [
        _row("o/a", "MRB", 1, 1, author_seat="ionos-7"),
        _row("o/a", "UAT", 2, 2, implementer_seat="ionos-7"),
        _row("o/a", "FR", 3, 3, needs_human=True),
        _row("o/a", "FR", 4, 4, giveup_seats="ionos-7"),
        _row("o/a", "FR", 5, 5),
    ])
    for task, num in (("MRB", "#1"), ("UAT", "#2"), ("FR", "#3"), ("FR", "#4")):
        st, why = gitclaim.assign_row(_home, "ionos-7", "o/a", task, num)
        assert st == "refused", (task, num, why)
    assert gitclaim.assign_row(_home, "ionos-7", "o/a", "FR", "#99")[0] == "refused"   # not queued
    monkeypatch.setattr(gitclaim, "worker_working_on", lambda h, n: "doing something")
    st, why = gitclaim.assign_row(_home, "ionos-7", "o/a", "FR", "#5")
    assert st == "refused" and "busy" in why
    monkeypatch.setattr(gitclaim, "worker_working_on", lambda h, n: "")
    assert gitclaim.assign_row(_home, "ionos-7", "o/a", "FR", "#5")[0] == "ok"
    # offered to ionos-7 just now: another seat cannot take it
    assert gitclaim.assign_row(_home, "ionos-8", "o/a", "FR", "#5")[0] == "refused"


def test_assign_repo_short_name_matches(_home):
    _queue(_home, [_row("Own/bob", "FR", 1, 1)])
    assert gitclaim.assign_row(_home, "ionos-7", "bob", "FR", "1")[0] == "ok"

def test_giveup_records_seat_and_blocks_reoffer_after_cooldown(_home):
    import shop_listen

    gitclaim._write_queue(gitclaim.queue_path(_home), {"v": 1, "unaccepted": [], "accepted": [
        {**_row("o/a", "UAT", 1, 1), "nick": "ionos-11", "channel": "#ionos"}]})
    t0 = time.time()
    st, job = shop_listen.return_job_to_unaccepted(_home, repo="o/a", task="UAT", ident="#1", now=t0)
    assert st == "ok" and job["giveup_seats"] == "ionos-11"
    fi.handle_focus_cmd(_home, "1 o/a")
    later = t0 + gitclaim.GIVEUP_COOLDOWN_S + 5
    assert gitclaim.offer_focus_top(_home, "ionos-11", "#ionos", now=later)[0] == "empty"
    assert gitclaim.offer_focus_top(_home, "ionos-12", "#ionos", now=later)[0] == "ok"
