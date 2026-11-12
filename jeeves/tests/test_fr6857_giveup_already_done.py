"""FR #6857: stray GIVEUP/NACK on an already-DONE shop row is a no-op.

A seat handing back one MRB must not reopen or ledger-giveup another row that
already sits in done[] (PASS/FAIL/CLOSED). Stale accepted twins of a done row
are dropped without returning to unaccepted.
"""
from __future__ import annotations

from pathlib import Path

import gitclaim
import registered_machines
import shop_listen

REPO = "SimonBarnett/agentic_fomprep"
NICK = "flamingo-6524"
SHOP = "#flamingo"


def _seed_roster(home: Path) -> None:
    registered_machines.save_registered(home, {"flamingo", "marchhare"})


def _mrb(num: int, **kw):
    r = {
        "repo": REPO,
        "task": "MRB",
        "id": f"#{num}",
        "seq": num,
        "ts": "2026-11-12T14:00:00Z",
        "line": f"MRB {REPO}#{num}",
        "title": f"mrb {num}",
        "url": f"https://github.com/{REPO}/pull/{num}",
        "state": "open",
    }
    r.update(kw)
    return r


def _done_pass(num: int, nick: str = "flamingo-1") -> dict:
    r = _mrb(num, result="PASS", done_ts="2026-11-12T13:00:00Z", done_by=nick)
    r.pop("state", None)
    return r


def test_giveup_on_done_pass_is_already_done_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _seed_roster(tmp_path)
    held = _mrb(464, nick=NICK, accepted_ts="2026-11-12T14:01:00Z")
    finished = _done_pass(463)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [held],
            "done": [finished],
        },
    )
    result = shop_listen.handle_shop_worker_line(
        tmp_path,
        nick=NICK,
        channel=SHOP,
        body=f"GIVEUP MRB {REPO}#463",
        post_fn=lambda _p: 204,
    )
    assert result["handled"] is True
    assert result["verb"] == "GIVEUP"
    assert result["status"] == "already-done"
    assert result.get("webhook") is None
    q = gitclaim.load_queue(tmp_path)
    assert [r.get("id") for r in (q.get("accepted") or [])] == ["#464"]
    assert not (q.get("unaccepted") or [])
    done = q.get("done") or []
    assert len(done) == 1
    assert done[0]["id"] == "#463"
    assert done[0]["result"] == "PASS"
    led = gitclaim.ledger_load(tmp_path)
    gu = (led.get("giveup") or {}).get(f"{REPO.lower()}#463") or {}
    assert NICK.lower() not in {str(k).lower() for k in gu}


def test_nack_on_done_does_not_requeue(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _seed_roster(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [],
            "done": [_done_pass(463)],
        },
    )
    result = shop_listen.handle_shop_worker_line(
        tmp_path,
        nick=NICK,
        channel=SHOP,
        body=f"NACK MRB {REPO}#463",
        post_fn=lambda _p: 204,
    )
    assert result["status"] == "already-done"
    q = gitclaim.load_queue(tmp_path)
    assert not (q.get("unaccepted") or [])
    assert (q.get("done") or [])[0]["result"] == "PASS"


def test_giveup_drops_stale_accepted_twin_of_done_pass(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _seed_roster(tmp_path)
    stale = _mrb(463, nick=NICK, accepted_ts="2026-11-12T14:01:00Z")
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [stale],
            "done": [_done_pass(463, nick="flamingo-99")],
        },
    )
    result = shop_listen.handle_shop_worker_line(
        tmp_path,
        nick=NICK,
        channel=SHOP,
        body=f"GIVEUP MRB {REPO}#463 self-mrb",
        post_fn=lambda _p: 204,
    )
    assert result["status"] == "already-done"
    q = gitclaim.load_queue(tmp_path)
    assert not (q.get("accepted") or [])
    assert not (q.get("unaccepted") or [])
    assert (q.get("done") or [])[0]["result"] == "PASS"


def test_live_giveup_of_accepted_not_in_done_still_returns(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _seed_roster(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [_mrb(464, nick=NICK, accepted_ts="t")],
            "done": [_done_pass(463)],
        },
    )
    result = shop_listen.handle_shop_worker_line(
        tmp_path,
        nick=NICK,
        channel=SHOP,
        body=f"GIVEUP MRB {REPO}#464 self-mrb",
        post_fn=lambda _p: 204,
    )
    assert result["status"] == "ok"
    q = gitclaim.load_queue(tmp_path)
    ids_u = [r.get("id") for r in (q.get("unaccepted") or [])]
    assert "#464" in ids_u
    assert (q.get("done") or [])[0]["id"] == "#463"


def test_format_shop_listen_info_notes_already_done():
    line = shop_listen.format_shop_listen_info(
        {"verb": "GIVEUP", "status": "already-done", "activity": None, "webhook": None, "reason": ""},
        nick=NICK,
    )
    assert "already-done" in line
    assert "note=stray-giveup-done-noop" in line


def test_irc_agent_skips_idle_on_already_done_giveup():
    text = (Path(__file__).resolve().parents[2] / "common" / "scripts" / "irc_agent.py").read_text(
        encoding="utf-8"
    )
    assert "already-done" in text
    assert "stray-giveup-done" in text or "FR #6857" in text
