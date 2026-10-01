"""#39 gaps 1-3: real seat nicks, focus-ordered FR|MRB|UAT assignment, !focus/strict/!ignore."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines
import shop_listen


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("JEEVES_OWNER_ACCOUNT", "simon")
    for k in ("JEEVES_FOCUS_MUTATORS", "JEEVES_FOCUS_MUTATOR_ACCOUNTS"):
        monkeypatch.delenv(k, raising=False)
    registered_machines.save_registered(tmp_path, {"ionos", "ce-priority-dev1", "win-mpre8vi4u6u"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def _row(repo, task, num, seq, **kw):
    r = {"repo": repo, "task": task, "id": f"#{num}", "seq": seq,
         "ts": f"2026-10-01T10:00:{seq:02d}Z", "line": "x"}
    r.update(kw)
    return r


def _queue(home, rows):
    gitclaim._write_queue(gitclaim.queue_path(home), {"v": 1, "unaccepted": rows, "accepted": []})


# ------------------------------------------------------------ gap 1: nicks
@pytest.mark.parametrize("nick,mid,pid", [
    ("ionos-12916", "ionos", "12916"),
    ("ce-priority-dev1-13204", "ce-priority-dev1", "13204"),
    ("win-mpre8vi4u6u-8412", "win-mpre8vi4u6u", "8412"),
    ("w-io-123", "win-mpre8vi4u6u", "123"),  # legacy w-<short>-<pid> alias
])
def test_real_seat_nicks_parse(nick, mid, pid):
    assert bobreport.parse_seat_nick(nick) == (mid, pid)
    assert gitclaim.worker_shop_channel(nick) == f"#{mid}"
    assert gitclaim.canonical_worker_nick(nick)


@pytest.mark.parametrize("nick", ["bob-ionos", "Jeeves", "simon", "ionos-", "ionos-abc", "ionos-0",
                                  "unregistered-123", "ce-123", "ionos_12"])
def test_non_seats_rejected(nick):
    assert bobreport.parse_seat_nick(nick) is None
    assert gitclaim.worker_shop_channel(nick) is None


def test_longest_machine_id_wins_ce_priority_dev1():
    assert bobreport.parse_seat_nick("ce-priority-dev1-5")[0] == "ce-priority-dev1"


def test_unregistered_machine_is_not_a_seat(_home):
    registered_machines.save_registered(_home, {"ionos"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    assert bobreport.parse_seat_nick("win-mpre8vi4u6u-8412") is None


def test_shop_listen_accepts_registered_machine_seat():
    assert shop_listen.is_shop_worker_nick("win-mpre8vi4u6u-8412", "#win-mpre8vi4u6u")
    assert not shop_listen.is_shop_worker_nick("win-mpre8vi4u6u-8412", "#ionos")  # own shop only


def test_bored_gate_ok_in_own_shop_ignored_elsewhere(_home):
    now = time.time()
    assert gitclaim.bored_gate(_home, "ce-priority-dev1-13204", "#ce-priority-dev1", now) == "ok"
    assert gitclaim.bored_gate(_home, "ce-priority-dev1-13204", "#ionos", now) == "ignore"
    assert gitclaim.bored_gate(_home, "ionos-12916", "#ionos", now) == "ok"


# ------------------------------------------------------------ gap 2: ordering
def test_focus_order_item_then_repo_then_seq(_home):
    _queue(_home, [_row("o/a", "FR", 1, 1), _row("o/b", "FR", 2, 2), _row("o/c", "MRB", 3, 3), _row("o/d", "UAT", 4, 4)])
    fi.handle_focus_cmd(_home, "o/b")          # repo focus high
    fi.handle_focus_cmd(_home, "o/d#4")        # item focus beats repo focus
    got = [r["id"] for r in gitclaim.ordered_unaccepted(_home)]
    assert got == ["#4", "#2", "#1", "#3"]


def test_item_rank_ordering_between_items(_home):
    _queue(_home, [_row("o/a", "FR", 1, 1), _row("o/a", "FR", 2, 2)])
    fi.handle_focus_cmd(_home, "o/a#2")
    fi.handle_focus_cmd(_home, "o/a#1")        # later item gets a later rank
    assert [r["id"] for r in gitclaim.ordered_unaccepted(_home)] == ["#2", "#1"]


def test_strict_focus_hides_unfocused(_home):
    _queue(_home, [_row("o/a", "FR", 1, 1), _row("o/b", "FR", 2, 2)])
    fi.handle_focus_cmd(_home, "o/b")
    fi.handle_focus_cmd(_home, "strict on")
    assert [r["id"] for r in gitclaim.ordered_unaccepted(_home)] == ["#2"]
    fi.handle_unfocus_cmd(_home, "o/b")
    assert gitclaim.ordered_unaccepted(_home) == []     # strict + nothing focused => nothing queued


def test_ignored_repo_is_never_assigned(_home):
    _queue(_home, [_row("o/a", "FR", 1, 1), _row("o/b", "FR", 2, 2)])
    fi.handle_ignore_cmd(_home, "o/a")
    st, job = gitclaim.offer_focus_top(_home, "ionos-1", "#ionos")
    assert st == "ok" and job["repo"] == "o/b"


def test_assign_wire_line_format():
    row = _row("SimonBarnett/bobiverse", "FR", 39, 1)
    assert gitclaim.format_assign_line("ionos-12916", row) == \
        "ionos-12916: FR SimonBarnett/bobiverse#39 https://github.com/SimonBarnett/bobiverse/issues/39"
    mrb = _row("o/r", "MRB", 7, 1)
    assert gitclaim.format_assign_line("ionos-1", mrb).endswith("o/r#7 https://github.com/o/r/pull/7")
    legacy_pr = _row("o/r", "PR", 8, 1)
    assert gitclaim.format_assign_line("ionos-1", legacy_pr).startswith("ionos-1: FR o/r#8 ")
    assert "ASSIGN" not in gitclaim.format_assign_line("ionos-1", row)


def test_offer_focus_top_stamps_and_ack_accepts(_home):
    _queue(_home, [_row("o/a", "FR", 1, 1), _row("o/b", "FR", 2, 2)])
    fi.handle_focus_cmd(_home, "o/b")
    st, job = gitclaim.offer_focus_top(_home, "win-mpre8vi4u6u-8412", "#win-mpre8vi4u6u")
    assert st == "ok" and job["repo"] == "o/b" and job["offered_to"] == "win-mpre8vi4u6u-8412"
    st2, acc = gitclaim.accept_offered(_home, "win-mpre8vi4u6u-8412", "#win-mpre8vi4u6u")
    assert st2 == "ok" and acc["id"] == "#2"
    assert [r["id"] for r in gitclaim.load_unaccepted(_home)] == ["#1"]


def test_row_offered_to_other_seat_is_skipped_then_reoffered_to_same_seat(_home):
    _queue(_home, [_row("o/a", "FR", 1, 1), _row("o/b", "FR", 2, 2)])
    t0 = time.time()
    s1, j1 = gitclaim.offer_focus_top(_home, "ionos-1", "#ionos", now=t0)
    s2, j2 = gitclaim.offer_focus_top(_home, "ionos-2", "#ionos", now=t0 + 5)
    assert (j1["id"], j2["id"]) == ("#1", "#2")          # one open offer per job
    s3, j3 = gitclaim.offer_focus_top(_home, "ionos-1", "#ionos", now=t0 + 6)
    assert j3["id"] == "#1"                              # rebroadcast, no second job burned
    s4, j4 = gitclaim.offer_focus_top(_home, "ionos-3", "#ionos", now=t0 + 200)   # offers expired
    assert j4["id"] == "#1"


def test_empty_queue_is_empty_status_and_line(_home):
    _queue(_home, [])
    assert gitclaim.offer_focus_top(_home, "ionos-1", "#ionos")[0] == "empty"
    assert gitclaim.format_nothing_queued("ionos-1") == "ionos-1: nothing queued"


def test_mrb_not_offered_to_author_seat_when_other_seat_live(_home):
    doc = bobreport.empty_digest()
    doc["machines"]["ionos"] = bobreport._empty_machine("ionos")
    doc["machines"]["ionos"]["workers"] = {"1": {"state": "idle"}, "2": {"state": "idle"}}
    bobreport.save_digest(_home, doc)
    _queue(_home, [_row("o/r", "MRB", 5, 1, author_seat="ionos-1"), _row("o/r", "FR", 6, 2)])
    st, job = gitclaim.offer_focus_top(_home, "ionos-1", "#ionos")
    assert job["id"] == "#6"                                  # skipped own MRB
    _queue(_home, [_row("o/r", "MRB", 5, 1, author_seat="ionos-1")])
    st, job = gitclaim.offer_focus_top(_home, "ionos-2", "#ionos")
    assert job["id"] == "#5"                                  # other seat may review it


def test_list_uses_same_order(_home):
    _queue(_home, [_row("o/a", "FR", 1, 1), _row("o/b", "FR", 2, 2)])
    fi.handle_focus_cmd(_home, "o/b")
    lines = gitclaim.format_unaccepted_list(_home)
    first_job = [l for l in lines if "o/" in l][0]
    assert "o/b" in first_job


# ------------------------------------------------------------ gap 3: commands + files
def test_focus_files_use_gh_jeeves_format(_home):
    fi.handle_focus_cmd(_home, "o/b")
    fi.handle_focus_cmd(_home, "high o/a#3")
    fi.handle_focus_cmd(_home, "strict on")
    d = json.loads((_home / "focus.json").read_text("utf-8"))
    assert d["v"] == 1 and d["strict"] is True
    assert d["repos"]["o/b"]["priority"] == 1
    assert d["items"]["o/a#3"]["rank"] == 1 and d["items"]["o/a#3"]["id"] == "#3"
    fi.handle_ignore_cmd(_home, "o/z")
    assert json.loads((_home / "ignored.json").read_text("utf-8"))["repos"] == ["o/z"]


def test_existing_ionos_style_files_are_read(_home):
    (_home / "focus.json").write_text(json.dumps({
        "v": 1, "strict": True,
        "items": {"SimonBarnett/bobiverse#39": {"id": "#39", "label": "high", "rank": 1,
                                                 "repo": "SimonBarnett/bobiverse", "ts": "t"}},
        "repos": {"bobiverse": {"label": "high", "priority": 1, "ts": "t"}}}), "utf-8")
    (_home / "ignored.json").write_text(json.dumps({"v": 1, "repos": ["noise/repo"]}), "utf-8")
    _queue(_home, [_row("SimonBarnett/bobiverse", "FR", 39, 5), _row("noise/repo", "FR", 1, 1),
                   _row("other/x", "FR", 2, 2)])
    assert [r["id"] for r in gitclaim.ordered_unaccepted(_home)] == ["#39"]


def test_bare_unfocus_and_all(_home):
    fi.handle_focus_cmd(_home, "o/b")
    fi.handle_focus_cmd(_home, "o/b#1")
    assert "removed" in fi.handle_unfocus_cmd(_home, "o/b#1")[0]
    assert "removed" in fi.handle_unfocus_cmd(_home, "o/b")[0]
    fi.handle_focus_cmd(_home, "o/q")
    assert "cleared" in fi.handle_unfocus_cmd(_home, "all")[0]
    assert fi.load_focus(_home)["repos"] == {}


def test_unignore_and_ignored_list(_home):
    fi.handle_ignore_cmd(_home, "o/z")
    assert fi.format_ignored_lines(_home) == ["ignored (1):", "  o/z"]
    assert "resumed" in fi.handle_unignore_cmd(_home, "o/z")[0]
    assert fi.format_ignored_lines(_home) == ["ignored: (none)"]


def test_ignore_purges_queued_rows(_home):
    _queue(_home, [_row("o/z", "FR", 1, 1), _row("o/y", "FR", 2, 2)])
    assert "purged 1" in fi.handle_ignore_cmd(_home, "o/z")[0]
    assert [r["repo"] for r in gitclaim.load_unaccepted(_home)] == ["o/y"]


def test_command_parsing():
    assert fi.parse_focus_cmd("!focus") == ""
    assert fi.parse_focus_cmd("!focus strict on") == "strict on"
    assert fi.parse_focus_cmd("!focusing") is None
    assert fi.parse_unfocus_cmd("!unfocus all") == "all"
    assert fi.parse_ignore_cmd("!ignore o/z") == "o/z"
    assert fi.is_ignored_cmd("!ignored")
    assert not fi.is_focus_family("!bored")
    assert not fi.is_focus_family("!list")


# ------------------------------------------------------------ permission
def test_permission_needs_owner_account_not_just_nick(_home):
    assert fi.dispatch(_home, "simon", "simon", "!focus o/a")[0].startswith("focus: o/a")
    assert fi.dispatch(_home, "simon", None, "!focus o/b")[0].startswith("focus: denied")   # nick alone
    assert fi.dispatch(_home, "simon-pc", "mallory", "!focus o/c")[0].startswith("focus: denied")
    assert fi.dispatch(_home, "mallory", "", "!focus strict on")[0].startswith("focus: denied")
    assert fi.dispatch(_home, "mallory", None, "!ignore o/a")[0].startswith("ignore: denied")
    assert fi.dispatch(_home, "mallory", None, "!unfocus all")[0].startswith("unfocus: denied")
    assert not fi.load_focus(_home)["strict"]
    assert list(fi.load_focus(_home)["repos"]) == ["o/a"]


def test_reads_are_open(_home):
    assert fi.dispatch(_home, "anyone", None, "!focus")[0] == "focus strict: off"
    assert fi.dispatch(_home, "anyone", None, "!focus strict")[0] == "focus strict: off"
    assert fi.dispatch(_home, "anyone", None, "!ignored") == ["ignored: (none)"]


def test_allowlist_env_is_additive(_home, monkeypatch):
    monkeypatch.setenv("JEEVES_FOCUS_MUTATORS", "bob-ionos")
    monkeypatch.setenv("JEEVES_FOCUS_MUTATOR_ACCOUNTS", "ops")
    assert fi.dispatch(_home, "bob-ionos", None, "!focus o/a")[0].startswith("focus: o/a")
    assert fi.dispatch(_home, "someone", "ops", "!focus o/b")[0].startswith("focus: o/b")
    assert fi.dispatch(_home, "bob-flamingo", None, "!focus o/c")[0].startswith("focus: denied")


def test_non_focus_body_returns_none(_home):
    assert fi.dispatch(_home, "simon", "simon", "hello") is None
    assert fi.dispatch(_home, "simon", "simon", "!bored") is None


def test_chair_wiring_present():
    t = (Path(__file__).resolve().parent.parent / "scripts" / "irc_agent.py").read_text("utf-8-sig")
    assert "import focus_ignore" in t
    assert "_maybe_focus_ignore" in t
    assert "gitclaim.offer_focus_top" in t
    assert "gitclaim.format_assign_line(src, job)" in t
    assert "ASSIGN {line}" not in t
