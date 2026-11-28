"""FR #7926: idle free-model seats take FR/FIX before paid or Grok seats."""
from __future__ import annotations

import json
import time

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
    registered_machines.save_registered(
        tmp_path, {"redqueen", "marchhare", "flamingo", "win-mpre8vi4u6u"}
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    (tmp_path / "models-catalog.json").write_text(
        json.dumps(
            {
                "agents": [
                    {
                        "agent": "Opencode-Free",
                        "cli": "Opencode",
                        "model": "opencode/deepseek-v4.1-flash-free",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def _row(repo, task, num, seq, **kw):
    r = {
        "repo": repo,
        "task": task,
        "id": f"#{num}",
        "seq": seq,
        "ts": f"2026-11-16T12:00:{seq:02d}Z",
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
            "updated": "2026-11-16T12:22:00Z",
            "kind": kind,
            "start_model": start_model,
            "configured_model": configured_model,
        }
    )


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
        "2002",
        kind="grok",
        start_model="grok-4",
        configured_model="grok-4",
    )
    bobreport.save_digest(home, doc)


def test_idle_free_seat_takes_the_fr_ahead_of_grok(_home):
    _queue(_home, [_row("SimonBarnett/bobiverse", "FR", 7926, 1)])
    fi.handle_focus_cmd(_home, "hi bobiverse")
    _save_pair(_home)
    st, job = gitclaim.offer_focus_top(_home, "flamingo-2002", "#flamingo")
    assert st != "ok" or job is None
    st, job = gitclaim.offer_focus_top(_home, "marchhare-1001", "#marchhare")
    assert st == "ok"
    assert job is not None
    assert str(job.get("task")).upper() == "FR"
    assert str(job.get("id")) == "#7926"


def test_busy_free_seat_does_not_delay_the_paid_offer(_home):
    _queue(_home, [_row("SimonBarnett/bobiverse", "FR", 7926, 1)])
    fi.handle_focus_cmd(_home, "hi bobiverse")
    _save_pair(_home, free_state="doing", free_work="MRB SimonBarnett/bobiverse#1")
    started = time.monotonic()
    st, job = gitclaim.offer_focus_top(_home, "flamingo-2002", "#flamingo")
    assert time.monotonic() - started < 2.0
    assert st == "ok"
    assert str(job.get("task")).upper() == "FR"


def test_ineligible_free_seat_yields_to_the_next_seat(_home):
    row = _row(
        "SimonBarnett/bobiverse",
        "FR",
        7926,
        1,
        cooldown_until="2099-01-01T00:00:00Z",
        giveup_seats="marchhare-1001",
        require_machine="flamingo",
        require_machine_operator=True,
    )
    _queue(_home, [row])
    fi.handle_focus_cmd(_home, "hi bobiverse")
    _save_pair(_home)
    st, job = gitclaim.offer_focus_top(_home, "marchhare-1001", "#marchhare")
    assert st != "ok" or job is None
    st, job = gitclaim.offer_focus_top(_home, "flamingo-2002", "#flamingo")
    assert st == "ok"
    assert str(job.get("id")) == "#7926"


def test_mrb_is_never_offered_to_a_free_seat(_home):
    _queue(
        _home,
        [
            _row("SimonBarnett/bobiverse", "MRB", 7888, 1),
            _row("SimonBarnett/bobiverse", "FR", 7926, 2),
        ],
    )
    fi.handle_focus_cmd(_home, "hi bobiverse")
    _save_pair(_home)
    st, job = gitclaim.offer_focus_top(_home, "marchhare-1001", "#marchhare")
    assert st == "ok"
    assert str(job.get("task")).upper() == "FR"
    st, job = gitclaim.offer_focus_top(_home, "flamingo-2002", "#flamingo")
    assert st == "ok"
    assert str(job.get("task")).upper() == "MRB"


def test_eligibility_uses_start_model_not_configured_model(_home):
    assert gitclaim.seat_started_on_free_model(_home, "nobody") is False
    _save_pair(_home)
    assert gitclaim.seat_started_on_free_model(_home, "marchhare-1001") is True
    assert gitclaim.seat_started_on_free_model(_home, "flamingo-2002") is False
    doc = bobreport.load_digest(_home)
    doc["machines"]["flamingo"]["workers"]["2002"]["start_model"] = "opencode-go/deepseek-v4-pro"
    doc["machines"]["flamingo"]["workers"]["2002"]["configured_model"] = (
        "opencode/deepseek-v4.1-flash-free"
    )
    bobreport.save_digest(_home, doc)
    assert gitclaim.seat_started_on_free_model(_home, "flamingo-2002") is False
