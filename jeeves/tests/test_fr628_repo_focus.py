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
    _queue(_home, [_row("o/a", "FR", 1, 1), _row("o/a", "UAT", 3, 3, repo_uat=True), _row("o/a", "MRB", 4, 4), _row("o/b", "MRB", 5, 5)])
    assert _ids(_home) == [("MRB", "#4"), ("UAT", "#3"), ("FR", "#1")]


def test_repo_focus_orders_repos_by_priority_then_entry_time(_home):
    _queue(_home, [_row("o/c", "MRB", 1, 1), _row("o/a", "FR", 2, 2), _row("o/b", "FR", 3, 3), _row("o/b", "UAT", 4, 4, repo_uat=True)])
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
        _row("o/a", "UAT", 1, 1),                                      # legacy per-PR UAT (t853u): never real work
        _row("o/a", "UAT", 2, 2, repo_uat=True),                       # the single repo-level UAT
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
    # t853u / #781: only repo-level UAT is offerable
    _queue(_home, [_row("o/a", "UAT", 0, 1, repo_uat=True, author_seat="ionos-11")])
    fi.handle_focus_cmd(_home, "1 o/a")
    assert gitclaim.offer_focus_top(_home, "ionos-11", "#ionos")[0] == "empty"
    assert gitclaim.offer_focus_top(_home, "ionos-12", "#ionos")[0] == "ok"


def test_never_reoffer_row_to_seat_that_gave_it_up(_home):
    _queue(
        _home,
        [
            _row("o/a", "UAT", 0, 1, repo_uat=True, giveup_seats="ionos-11"),
            _row("o/a", "FR", 2, 2),
        ],
    )
    fi.handle_focus_cmd(_home, "1 o/a")
    st, job = gitclaim.offer_focus_top(_home, "ionos-11", "#ionos")
    assert (job["task"], job["id"]) == ("FR", "#2")
    st, job = gitclaim.offer_focus_top(_home, "ionos-12", "#ionos")
    assert (job["task"], job["id"]) == ("UAT", "#0")


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
        {**_row("o/a", "UAT", 0, 1, repo_uat=True), "nick": "ionos-11", "channel": "#ionos"}]})
    t0 = time.time()
    st, job = shop_listen.return_job_to_unaccepted(_home, repo="o/a", task="UAT", ident="#0", now=t0)
    assert st == "ok" and job["giveup_seats"] == "ionos-11"
    fi.handle_focus_cmd(_home, "1 o/a")
    later = t0 + gitclaim.GIVEUP_COOLDOWN_S + 5
    assert gitclaim.offer_focus_top(_home, "ionos-11", "#ionos", now=later)[0] == "empty"
    assert gitclaim.offer_focus_top(_home, "ionos-12", "#ionos", now=later)[0] == "ok"

# ------------------------------------------------------------ t852u: durable seat ledger
def _uat(num, refs=(), **kw):
    # Default repo-level UAT (#781 / t853u); callers may override id via num=0 + repo_uat.
    r = _row("o/a", "UAT", num, num, refs=list(refs), repo_uat=True)
    r.update(kw)
    return r


def test_ledger_giveup_survives_row_rebuild_and_blocks_reoffer(_home):
    """GitHub resync rebuilds rows (no giveup stamps): the seat must still never get the row back."""
    import shop_listen

    _queue(_home, [_uat(0, refs=["#9"], offered_to="ionos-11", offered_ts=_now_iso(30), offered_channel="#ionos")])
    gitclaim.accept_offered(_home, "ionos-11", "#ionos")
    shop_listen.handle_shop_worker_line(_home, nick="ionos-11", channel="#ionos",
                                        body="GIVEUP UAT o/a#0 self-UAT", post_fn=lambda p: 204)
    _queue(_home, [_uat(0, refs=["#9"])])                      # resync wiped every stamp
    fi.handle_focus_cmd(_home, "1 o/a")
    assert gitclaim.offer_focus_top(_home, "ionos-11", "#ionos")[0] == "empty"
    assert gitclaim.offer_focus_top(_home, "ionos-12", "#ionos")[0] == "ok"


def test_ledger_blocks_fr_implementer_and_mrb_reviewer_for_uat_family(_home):
    gitclaim.ledger_touch(_home, "ionos-11", "o/a", "FR", ["o/a#269"])        # implemented FR #269
    gitclaim.ledger_touch(_home, "ionos-12", "o/a", "MRB", ["o/a#623", "o/a#269"])   # reviewed PR #623 closing #269
    led = gitclaim.ledger_load(_home)
    # t853u / #781: repo-level UAT only blocks FR implementers (not MRB reviewers).
    uat = _uat(0, refs=["#269"], merged_prs=["#623"])
    assert "no self-UAT" in gitclaim.ledger_blocks(led, uat, "ionos-11")
    assert gitclaim.ledger_blocks(led, uat, "ionos-12") == ""
    assert gitclaim.ledger_blocks(led, uat, "ionos-13") == ""
    mrb = _row("o/a", "MRB", 623, 1, refs=["#269"])
    assert gitclaim.ledger_blocks(led, mrb, "ionos-11")          # implementer can't review own PR
    assert gitclaim.ledger_blocks(led, mrb, "ionos-12") == ""     # reviewer may re-review


def test_done_fr_with_pr_url_records_implementer_for_pr_family(_home):
    import shop_listen

    _queue(_home, [], )
    gitclaim._write_queue(gitclaim.queue_path(_home), {"v": 1, "unaccepted": [], "accepted": [
        {**_row("o/a", "FR", 7, 1), "nick": "ionos-11", "channel": "#ionos"}]})
    shop_listen.handle_shop_worker_line(_home, nick="ionos-11", channel="#ionos",
                                        body="DONE FR o/a#7 https://github.com/o/a/pull/12", post_fn=lambda p: 204)
    led = gitclaim.ledger_load(_home)
    # t860u: DONE FR (even with a PR url: it may be an EXISTING PR) is informational ("FRW"), not authorship
    assert led["touch"]["o/a#12"]["ionos-11"] == ["FRW"] and led["touch"]["o/a#7"]["ionos-11"] == ["FRW"]
    assert not gitclaim.ledger_blocks(led, _row("o/a", "MRB", 12, 2, refs=["#7"]), "ionos-11")


def test_done_existing_pr_and_uat_giveup_do_not_block_mrb_of_the_pr(_home):
    """t860u: only the PR's real author (commit authors -> role FR) is blocked from reviewing it."""
    gitclaim.ledger_note_event(_home, "ionos-11", "ACK", "FR", "o/a", "#686", {"refs": ["#660"]})
    gitclaim.ledger_note_event(_home, "ionos-11", "DONE", "FR", "o/a", "#686", {"refs": ["#660"]}, result="DONE existing PR #660, no duplicate")
    gitclaim.ledger_note_event(_home, "ionos-11", "GIVEUP", "UAT", "o/a", "#640", {"refs": ["#696"]})
    mrb = _row("o/a", "MRB", 660, 1, refs=["#686", "#640"])
    led = gitclaim.ledger_load(_home)
    assert gitclaim.ledger_blocks(led, mrb, "ionos-11") == ""                       # did not write #660
    assert gitclaim.ledger_blocks(led, _row("o/a", "MRB", 696, 2, refs=["#640"]), "ionos-11") == ""   # UAT giveup != MRB giveup
    gitclaim.ledger_note_event(_home, "ionos-11", "GIVEUP", "MRB", "o/a", "#700", {"refs": ["#701"]})
    assert gitclaim.ledger_blocks(gitclaim.ledger_load(_home), _row("o/a", "MRB", 701, 3, refs=["#700"]), "ionos-11")   # same kind still blocks
    gitclaim.ledger_refresh_authors(_home, [mrb], lambda repo, num: {"ionos-12"} if num == "660" else set())
    led = gitclaim.ledger_load(_home)
    assert gitclaim.ledger_blocks(led, mrb, "ionos-12")                              # the real author is blocked
    assert gitclaim.ledger_blocks(led, mrb, "ionos-11") == ""


def test_offer_and_assign_honour_ledger_even_without_row_stamps(_home):
    gitclaim.ledger_touch(_home, "ionos-11", "o/a", "FR", ["o/a#611", "o/a#626"])
    _queue(_home, [_uat(611, refs=["#626"]), _row("o/a", "FR", 8, 9)])
    fi.handle_focus_cmd(_home, "1 o/a")
    st, job = gitclaim.offer_focus_top(_home, "ionos-11", "#ionos")
    assert (job["task"], job["id"]) == ("FR", "#8")
    st, why = gitclaim.assign_row(_home, "ionos-11", "o/a", "UAT", "#611")
    assert st == "refused" and "no self-UAT" in why
    assert gitclaim.assign_row(_home, "ionos-12", "o/a", "UAT", "#611")[0] == "ok"

def test_ledger_refresh_from_pr_commit_authors(_home):
    rows = [_row("o/a", "MRB", 12, 1, refs=["#7"]), _uat(30, refs=["#31"])]
    calls = []

    def fetch(repo, num):
        calls.append(num)
        return {"ionos-11"} if num == "12" else (set() if num == "30" else None)

    assert gitclaim.ledger_refresh_authors(_home, rows, fetch) == 3 - 1     # #31 unknown -> retried later
    led = gitclaim.ledger_load(_home)
    assert led["touch"]["o/a#12"]["ionos-11"] == ["FR"] and led["touch"]["o/a#7"]["ionos-11"] == ["FR"]
    assert gitclaim.ledger_blocks(led, rows[0], "ionos-11") and not gitclaim.ledger_blocks(led, rows[0], "ionos-12")
    calls.clear()
    gitclaim.ledger_refresh_authors(_home, rows, fetch)
    assert calls == ["31"] or calls == ["7", "31"] or "12" not in calls    # cached keys are not re-fetched

# ------------------------------------------------------------ t853u: UAT is per REPO
def _gh(issues=(), open_prs=(), merged=(), repo="o/a"):
    """fetch_json seam: open issues / open PRs / closed PRs for one repo."""
    def get(url):
        if f"/repos/{repo}/issues?" in url:
            return list(issues)
        if f"/repos/{repo}/pulls?state=open" in url:
            return list(open_prs)
        if f"/repos/{repo}/pulls?state=closed" in url:
            return list(merged)
        raise RuntimeError("404 " + url)
    return get


def _merged_pr(num, closes=None, age_s=600):
    return {"number": num, "title": f"pr {num}", "body": f"Closes #{closes}" if closes else "", "merged_at": _now_iso(age_s)}


def _uats(home):
    return [r for r in gitclaim.load_unaccepted(home) if r["task"] == "UAT"]


def test_merge_webhook_queues_no_per_pr_uat(_home):
    gitclaim.apply_queue_event(_home, gitclaim.claim_from_payload("pull_request", {
        "action": "closed", "repository": {"full_name": "o/a"},
        "pull_request": {"number": 9, "title": "t", "body": "Closes #5", "merged": True, "html_url": "u"}}))
    assert _uats(_home) == []


def test_repo_uat_row_created_once_when_repo_is_clear(_home):
    get = _gh(merged=[_merged_pr(10, closes=3), _merged_pr(11)])
    res = gitclaim.resync_from_github(_home, ["o/a"], fetch_json=get)
    assert res["ok"]
    (u,) = _uats(_home)
    assert (u["id"], u["repo"]) == ("#0", "o/a") and u["repo_uat"] is True
    assert u["merged_prs"] == ["#10", "#11"] and "#3" in u["refs"]
    assert u["url"] == "https://github.com/o/a"
    assert gitclaim.format_assign_line("ionos-1", u) == "ionos-1: UAT o/a#0 https://github.com/o/a"
    gitclaim.resync_from_github(_home, ["o/a"], fetch_json=get)       # idempotent: still ONE row
    assert len(_uats(_home)) == 1


def test_open_issue_or_open_pr_holds_uat_back_but_excluded_issues_do_not(_home):
    merged = [_merged_pr(10)]
    gitclaim.resync_from_github(_home, ["o/a"], fetch_json=_gh(issues=[{"number": 1, "title": "real work"}], merged=merged))
    assert _uats(_home) == []
    gitclaim.resync_from_github(_home, ["o/a"], fetch_json=_gh(open_prs=[{"number": 12, "title": "x", "body": ""}], merged=merged))
    assert _uats(_home) == []
    excluded = [
        {"number": 2, "title": "evergreen", "labels": [{"name": "mrb-home"}]},
        {"number": 3, "title": "human only", "labels": [{"name": "needs-human"}]},
        {"number": 4, "title": "harvest: skill notes"},
        {"number": 5, "title": "a PR", "pull_request": {"url": "x"}},
    ]
    gitclaim.resync_from_github(_home, ["o/a"], fetch_json=_gh(issues=excluded, merged=merged))
    assert len(_uats(_home)) == 1


def test_no_merges_this_cycle_no_uat_and_done_resets_the_cycle(_home):
    import shop_listen

    old = [_merged_pr(10, age_s=5 * 86400)]
    gitclaim.resync_from_github(_home, ["o/a"], fetch_json=_gh(merged=old))
    assert _uats(_home) == []                                           # merged before the 48 h window: not this cycle
    get = _gh(merged=[_merged_pr(10, age_s=3600)])
    gitclaim.resync_from_github(_home, ["o/a"], fetch_json=get)
    assert len(_uats(_home)) == 1
    gitclaim._write_queue(gitclaim.queue_path(_home), {"v": 1, "unaccepted": [], "accepted": [
        {**_uats(_home)[0], "nick": "ionos-3", "channel": "#ionos"}]})
    shop_listen.handle_shop_worker_line(_home, nick="ionos-3", channel="#ionos", body="DONE UAT o/a#0 PASS", post_fn=lambda p: 204)
    gitclaim.resync_from_github(_home, ["o/a"], fetch_json=get)         # same merge, new cycle has started
    assert _uats(_home) == []


def test_repo_uat_dropped_when_repo_stops_being_clear(_home):
    merged = [_merged_pr(10)]
    gitclaim.resync_from_github(_home, ["o/a"], fetch_json=_gh(merged=merged))
    assert len(_uats(_home)) == 1
    gitclaim.resync_from_github(_home, ["o/a"], fetch_json=_gh(issues=[{"number": 7, "title": "new bug"}], merged=merged))
    assert _uats(_home) == []


def test_legacy_per_pr_uat_rows_are_pruned(_home):
    _queue(_home, [_row("o/a", "UAT", 269, 1), _row("o/a", "UAT", 611, 2), _row("o/a", "UAT", 0, 3, repo_uat=True), _row("o/a", "FR", 5, 4)])
    gitclaim.prune_unassignable_queue(_home)
    assert sorted((r["task"], r["id"]) for r in gitclaim.load_unaccepted(_home)) == [("FR", "#5"), ("UAT", "#0")]


def _repo_uat_row(**kw):
    r = _row("o/a", "UAT", 0, 1, repo_uat=True, merged_prs=["#10", "#11"], refs=["#10", "#11"], url="https://github.com/o/a")
    r.update(kw)
    return r


def test_repo_uat_goes_to_a_seat_that_implemented_none_of_the_merged_prs(_home, monkeypatch):
    gitclaim.ledger_touch(_home, "ionos-11", "o/a", "FR", ["o/a#10"])
    gitclaim.ledger_touch(_home, "ionos-12", "o/a", "MRB", ["o/a#10"])         # a reviewer may still run the UAT
    monkeypatch.setattr(gitclaim, "live_seat_nicks", lambda h: {"ionos-11", "ionos-12", "ionos-13"})
    _queue(_home, [_repo_uat_row()])
    fi.handle_focus_cmd(_home, "1 o/a")
    assert gitclaim.offer_focus_top(_home, "ionos-11", "#ionos")[0] == "empty"
    st, job = gitclaim.offer_focus_top(_home, "ionos-12", "#ionos")
    assert st == "ok" and (job["task"], job["id"]) == ("UAT", "#0")


def test_repo_uat_fallback_when_every_live_seat_implemented_something(_home, monkeypatch):
    gitclaim.ledger_touch(_home, "ionos-11", "o/a", "FR", ["o/a#10"])
    gitclaim.ledger_touch(_home, "ionos-12", "o/a", "FR", ["o/a#11"])
    monkeypatch.setattr(gitclaim, "live_seat_nicks", lambda h: {"ionos-11", "ionos-12"})
    _queue(_home, [_repo_uat_row()])
    fi.handle_focus_cmd(_home, "1 o/a")
    assert gitclaim.offer_focus_top(_home, "ionos-11", "#ionos")[0] == "ok"
    # ... but a seat that already gave the repo UAT up never gets it back
    gitclaim.ledger_giveup(_home, "ionos-12", "o/a", "UAT", "#0")
    assert gitclaim.offer_focus_top(_home, "ionos-12", "#ionos")[0] == "empty"


def test_repo_uat_pr_authors_are_not_smeared_across_merged_prs(_home):
    row = _repo_uat_row()
    gitclaim.ledger_refresh_authors(_home, [row], lambda repo, num: {"ionos-11"} if num == "10" else set())
    led = gitclaim.ledger_load(_home)
    assert led["touch"]["o/a#10"]["ionos-11"] == ["FR"]
    assert "ionos-11" not in led["touch"].get("o/a#11", {})              # wrote PR 10 only
    assert gitclaim.ledger_blocks(led, row, "ionos-11")
    assert not gitclaim.ledger_blocks(led, _row("o/a", "MRB", 11, 2), "ionos-11")

def test_resync_made_mrb_rows_carry_a_real_pull_url_and_are_offerable(_home):
    """t855u: resync-created MRB rows had no url, so mrb_row_offerable() hid EVERY open PR and seats sat idle."""
    pr = {"number": 21, "title": "x", "body": "Closes #5"}
    get = _gh(open_prs=[pr])
    gitclaim.resync_from_github(_home, ["o/a"], fetch_json=get)
    (m,) = [r for r in gitclaim.load_unaccepted(_home) if r["task"] == "MRB"]
    assert m["url"] == "https://github.com/o/a/pull/21" and gitclaim.mrb_row_offerable(m)
    # a legacy url-less row is healed on the next resync
    q = gitclaim.load_queue(_home)
    for r in q["unaccepted"]:
        r.pop("url", None)
    gitclaim._write_queue(gitclaim.queue_path(_home), q)
    assert not gitclaim.mrb_row_offerable(gitclaim.load_unaccepted(_home)[0])
    gitclaim.resync_from_github(_home, ["o/a"], fetch_json=get)
    fi.handle_focus_cmd(_home, "1 o/a")
    st, job = gitclaim.offer_focus_top(_home, "ionos-9", "#ionos")
    assert st == "ok" and (job["task"], job["id"]) == ("MRB", "#21")

def test_fr_done_is_not_reoffered_while_its_pr_waits(_home):
    import shop_listen

    gitclaim._write_queue(gitclaim.queue_path(_home), {"v": 1, "unaccepted": [], "accepted": [
        {**_row("o/a", "FR", 7, 1), "nick": "ionos-11", "channel": "#ionos"}]})
    shop_listen.handle_shop_worker_line(_home, nick="ionos-11", channel="#ionos",
                                        body="DONE FR o/a#7 https://github.com/o/other/pull/3", post_fn=lambda p: 204)
    _queue(_home, [_row("o/a", "FR", 7, 1), _row("o/a", "FR", 8, 2)])   # resync re-added the still-open issue
    fi.handle_focus_cmd(_home, "1 o/a")
    st, job = gitclaim.offer_focus_top(_home, "ionos-12", "#ionos")
    assert (job["task"], job["id"]) == ("FR", "#8")
    assert gitclaim.assign_row(_home, "ionos-12", "o/a", "FR", "#7")[0] == "refused"
