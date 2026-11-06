"""FR #6134: OpenCode seats skip hostile MRB/UAT offers; still get FR/FIX."""
from __future__ import annotations

import time
from pathlib import Path

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
    registered_machines.save_registered(tmp_path, {"redqueen", "marchhare", "win-mpre8vi4u6u"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def _row(repo, task, num, seq, **kw):
    r = {
        "repo": repo,
        "task": task,
        "id": f"#{num}",
        "seq": seq,
        "ts": f"2026-11-06T10:00:{seq:02d}Z",
        "line": "x",
    }
    if task == "MRB":
        r["url"] = f"https://github.com/{repo}/pull/{num}"
    r.update(kw)
    return r


def _queue(home, rows):
    gitclaim._write_queue(gitclaim.queue_path(home), {"v": 1, "unaccepted": rows, "accepted": []})


def _seed_kind(home, mid: str, pid: str, kind: str):
    doc = bobreport.empty_digest()
    doc["machines"][mid] = bobreport._empty_machine(mid)
    nick = f"{mid}-{pid}"
    doc["machines"][mid]["workers"] = {
        pid: {"state": "idle", "nick": nick, "kind": kind},
    }
    doc["machines"][mid]["worker_list"] = [
        {"nick": nick, "state": "idle", "work": "", "updated": "2026-11-06T10:00:00Z", "kind": kind},
    ]
    bobreport.save_digest(home, doc)


def test_seat_agent_kind_reads_digest(_home):
    _seed_kind(_home, "redqueen", "9388", "opencode")
    assert gitclaim.seat_agent_kind(_home, "redqueen-9388") == "opencode"
    assert gitclaim.seat_skips_hostile_review("opencode") is True
    assert gitclaim.seat_skips_hostile_review("grok") is False
    assert gitclaim.seat_skips_hostile_review("") is False


def test_opencode_skips_mrb_offer_fr_still_ok(_home):
    _queue(
        _home,
        [
            _row("SimonBarnett/bobiverse", "MRB", 6121, 1),
            _row("SimonBarnett/bobiverse", "FR", 6134, 2),
        ],
    )
    fi.handle_focus_cmd(_home, "hi bobiverse")
    _seed_kind(_home, "redqueen", "1001", "opencode")
    # Also seed a grok sibling so live set is non-empty for other gates
    doc = bobreport.load_digest(_home)
    doc["machines"]["redqueen"]["workers"]["2002"] = {
        "state": "idle",
        "nick": "redqueen-2002",
        "kind": "grok",
    }
    bobreport.save_digest(_home, doc)

    st, job = gitclaim.offer_focus_top(_home, "redqueen-1001", "#redqueen")
    assert st == "ok"
    assert job is not None
    assert str(job.get("task")).upper() == "FR"
    assert str(job.get("id")) == "#6134"


def test_grok_seat_still_gets_mrb(_home):
    _queue(_home, [_row("SimonBarnett/bobiverse", "MRB", 6121, 1)])
    fi.handle_focus_cmd(_home, "hi bobiverse")
    _seed_kind(_home, "redqueen", "3003", "grok")
    st, job = gitclaim.offer_focus_top(_home, "redqueen-3003", "#redqueen")
    assert st == "ok"
    assert str(job.get("task")).upper() == "MRB"


def test_assign_row_refuses_mrb_to_opencode(_home):
    _queue(_home, [_row("SimonBarnett/bobiverse", "MRB", 6121, 1)])
    _seed_kind(_home, "redqueen", "1001", "opencode")
    st, detail = gitclaim.assign_row(
        _home, "redqueen-1001", "SimonBarnett/bobiverse", "MRB", "6121"
    )
    assert st == "refused"
    assert "OpenCode" in str(detail) or "opencode" in str(detail).lower() or "6134" in str(detail)


def test_unknown_kind_does_not_block_mrb(_home):
    """Missing digest kind must not strand stronger seats that forgot to publish kind."""
    _queue(_home, [_row("SimonBarnett/bobiverse", "MRB", 6121, 1)])
    fi.handle_focus_cmd(_home, "hi bobiverse")
    _seed_kind(_home, "redqueen", "4004", "")  # unknown
    st, job = gitclaim.offer_focus_top(_home, "redqueen-4004", "#redqueen")
    assert st == "ok"
    assert str(job.get("task")).upper() == "MRB"
