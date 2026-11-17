"""FR #8138: when only Grok seats are up, older FR beats a newer MRB for that seat."""
from __future__ import annotations

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines
import pytest


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("JEEVES_OWNER_ACCOUNT", "simon")
    for k in ("JEEVES_FOCUS_MUTATORS", "JEEVES_FOCUS_MUTATOR_ACCOUNTS"):
        monkeypatch.delenv(k, raising=False)
    registered_machines.save_registered(
        tmp_path, {"redqueen", "marchhare", "flamingo", "win-mpre8vi4u6u"}
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def _row(repo, task, num, seq, **kw):
    r = {
        "repo": repo,
        "task": task,
        "id": f"#{num}",
        "seq": seq,
        "ts": f"2026-11-17T21:1{seq:01d}:00Z",
        "line": "x",
    }
    if task == "MRB":
        r["url"] = f"https://github.com/{repo}/pull/{num}"
    r.update(kw)
    return r


def _queue(home, rows):
    gitclaim._write_queue(
        gitclaim.queue_path(home), {"v": 1, "unaccepted": rows, "accepted": []}
    )


def _put_seat(doc, mid, pid, *, kind, start_model, configured_model="", state="idle", work=""):
    nick = f"{mid}-{pid}"
    ent = doc["machines"].setdefault(mid, bobreport._empty_machine(mid))
    workers = ent.setdefault("workers", {})
    workers[str(pid)] = {
        "state": state,
        "nick": nick,
        "kind": kind,
        "start_model": start_model,
        "configured_model": configured_model,
        "model": start_model,
        "working_on": work,
    }
    rows = ent.setdefault("worker_list", [])
    rows.append(
        {
            "nick": nick,
            "state": state,
            "work": work,
            "updated": "2026-11-17T21:20:00Z",
            "kind": kind,
            "start_model": start_model,
            "configured_model": configured_model,
        }
    )


def _save_grok_only(home):
    doc = bobreport.empty_digest()
    doc["machines"] = {}
    _put_seat(
        doc,
        "flamingo",
        "18800",
        kind="grok",
        start_model="grok-4",
        configured_model="grok-4",
    )
    bobreport.save_digest(home, doc)


def _save_pair(home, *, free_state="idle", free_work=""):
    doc = bobreport.empty_digest()
    doc["machines"] = {}
    _put_seat(
        doc,
        "marchhare",
        "1001",
        kind="opencode",
        start_model="opencode/deepseek-v4.1-flash-free",
        configured_model="opencode-go/deepseek-v4-pro",
        state=free_state,
        work=free_work,
    )
    _put_seat(
        doc,
        "flamingo",
        "18800",
        kind="grok",
        start_model="grok-4",
        configured_model="grok-4",
    )
    bobreport.save_digest(home, doc)


def test_only_grok_older_fr_before_newer_mrb(_home):
    # Toray-shaped: FR #8 queued (seq 1) then MRB #10/#11 (seq 2/3). Focus may rank MRB first.
    _queue(
        _home,
        [
            _row("SimonBarnett/toray", "FR", 8, 1),
            _row("SimonBarnett/toray", "MRB", 10, 2),
            _row("SimonBarnett/toray", "MRB", 11, 3),
        ],
    )
    fi.handle_focus_cmd(_home, "hi toray")
    _save_grok_only(_home)
    st, job = gitclaim.offer_focus_top(_home, "flamingo-18800", "#flamingo")
    assert st == "ok"
    assert job is not None
    assert str(job.get("task")).upper() == "FR"
    assert str(job.get("id")) == "#8"


def test_free_idle_fr_to_free_mrb_to_grok(_home):
    _queue(
        _home,
        [
            _row("SimonBarnett/toray", "FR", 8, 1),
            _row("SimonBarnett/toray", "MRB", 10, 2),
        ],
    )
    fi.handle_focus_cmd(_home, "hi toray")
    _save_pair(_home)
    st, job = gitclaim.offer_focus_top(_home, "flamingo-18800", "#flamingo")
    assert st == "ok"
    assert str(job.get("task")).upper() == "MRB"
    assert str(job.get("id")) == "#10"
    st, job = gitclaim.offer_focus_top(_home, "marchhare-1001", "#marchhare")
    assert st == "ok"
    assert str(job.get("task")).upper() == "FR"
    assert str(job.get("id")) == "#8"


def test_free_comes_up_while_fr_waits(_home):
    _queue(_home, [_row("SimonBarnett/toray", "FR", 8, 1)])
    fi.handle_focus_cmd(_home, "hi toray")
    # Free seat was busy — Grok may take the FR (7926 busy path).
    _save_pair(_home, free_state="doing", free_work="MRB SimonBarnett/bobiverse#1")
    st, job = gitclaim.offer_focus_top(_home, "flamingo-18800", "#flamingo")
    assert st == "ok"
    assert str(job.get("task")).upper() == "FR"
    # Reset offer pin and bring free seat idle: FR reserved for free.
    _queue(_home, [_row("SimonBarnett/toray", "FR", 8, 1)])
    _save_pair(_home, free_state="idle")
    st, job = gitclaim.offer_focus_top(_home, "flamingo-18800", "#flamingo")
    assert st != "ok" or job is None
    st, job = gitclaim.offer_focus_top(_home, "marchhare-1001", "#marchhare")
    assert st == "ok"
    assert str(job.get("id")) == "#8"


def test_mrb_queued_first_still_offered_to_grok(_home):
    # Older MRB before FR: Grok may take the MRB (FR was not queued first).
    _queue(
        _home,
        [
            _row("SimonBarnett/toray", "MRB", 10, 1),
            _row("SimonBarnett/toray", "FR", 8, 2),
        ],
    )
    fi.handle_focus_cmd(_home, "hi toray")
    _save_grok_only(_home)
    st, job = gitclaim.offer_focus_top(_home, "flamingo-18800", "#flamingo")
    assert st == "ok"
    assert str(job.get("task")).upper() == "MRB"
    assert str(job.get("id")) == "#10"
