"""FR #7562: GIVEUP/NACK/DONE shop handback is alias-equivalent for priority-mcp."""
from __future__ import annotations

import pytest

import gitclaim
import registered_machines
import shop_listen
from repo_alias import PRIORITY_MCP_ALIAS, PRIORITY_MCP_CANONICAL

NICK = "flamingo-6524"
SHOP = "#flamingo"


def _seed_roster(home):
    registered_machines.save_registered(home, {"flamingo", "marchhare"})


def _row(repo: str, num: int, task: str = "MRB", **kw):
    r = {
        "repo": repo,
        "task": task,
        "id": f"#{num}",
        "seq": num,
        "ts": "2026-11-12T14:00:00Z",
        "line": f"{task} {repo}#{num}",
        "title": f"{task.lower()} {num}",
        "url": f"https://github.com/{repo}/pull/{num}",
        "state": "open",
    }
    r.update(kw)
    return r


def _done_pass(repo: str, num: int, nick: str = "flamingo-1") -> dict:
    r = _row(repo, num, result="PASS", done_ts="2026-11-12T13:00:00Z", done_by=nick)
    r.pop("state", None)
    return r


@pytest.mark.parametrize("stored,wire", [
    (PRIORITY_MCP_CANONICAL, PRIORITY_MCP_ALIAS),
    (PRIORITY_MCP_ALIAS, PRIORITY_MCP_CANONICAL),
    (PRIORITY_MCP_CANONICAL, PRIORITY_MCP_CANONICAL),
])
def test_giveup_already_done_across_alias_spellings(tmp_path, monkeypatch, stored, wire):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _seed_roster(tmp_path)
    other_a = _row(PRIORITY_MCP_CANONICAL, 900, nick="other-1", accepted_ts="t")
    other_d = _done_pass(PRIORITY_MCP_CANONICAL, 901)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [other_a],
            "done": [_done_pass(stored, 463), other_d],
        },
    )
    result = shop_listen.handle_shop_worker_line(
        tmp_path,
        nick=NICK,
        channel=SHOP,
        body=f"GIVEUP MRB {wire}#463",
        post_fn=lambda _p: 204,
    )
    assert result["status"] == "already-done"
    q = gitclaim.load_queue(tmp_path)
    assert not (q.get("unaccepted") or [])
    assert any(r.get("id") == "#463" and r.get("result") == "PASS" for r in (q.get("done") or []))
    assert any(r.get("id") == "#900" for r in (q.get("accepted") or []))
    assert any(r.get("id") == "#901" for r in (q.get("done") or []))


@pytest.mark.parametrize("stored,wire", [
    (PRIORITY_MCP_CANONICAL, PRIORITY_MCP_ALIAS),
    (PRIORITY_MCP_ALIAS, PRIORITY_MCP_CANONICAL),
])
def test_giveup_live_accepted_requeues_across_alias(tmp_path, monkeypatch, stored, wire):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _seed_roster(tmp_path)
    import stall_callbacks
    monkeypatch.setattr(stall_callbacks, "emit_giveup", lambda home, **kw: True)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [_row(stored, 464, nick=NICK, accepted_ts="t")],
            "done": [_done_pass(stored, 463)],
        },
    )
    result = shop_listen.handle_shop_worker_line(
        tmp_path,
        nick=NICK,
        channel=SHOP,
        body=f"GIVEUP MRB {wire}#464",
        post_fn=lambda _p: 204,
    )
    assert result["status"] == "ok"
    q = gitclaim.load_queue(tmp_path)
    assert any(r.get("id") == "#464" for r in (q.get("unaccepted") or []))


def test_giveup_missing_when_no_row(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _seed_roster(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": []},
    )
    result = shop_listen.handle_shop_worker_line(
        tmp_path,
        nick=NICK,
        channel=SHOP,
        body=f"GIVEUP MRB {PRIORITY_MCP_ALIAS}#463",
        post_fn=lambda _p: 204,
    )
    assert result["status"] == "missing"


@pytest.mark.parametrize("stored,wire", [
    (PRIORITY_MCP_CANONICAL, PRIORITY_MCP_ALIAS),
    (PRIORITY_MCP_ALIAS, PRIORITY_MCP_CANONICAL),
])
def test_done_ok_and_duplicate_across_alias(tmp_path, monkeypatch, stored, wire):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _seed_roster(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [_row(stored, 500, nick=NICK, accepted_ts="t")],
            "done": [],
        },
    )
    r1 = shop_listen.handle_shop_worker_line(
        tmp_path,
        nick=NICK,
        channel=SHOP,
        body=f"DONE MRB {wire}#500 PASS https://example.test/pr/500",
        post_fn=lambda _p: 204,
    )
    assert r1["status"] == "ok"
    r2 = shop_listen.handle_shop_worker_line(
        tmp_path,
        nick=NICK,
        channel=SHOP,
        body=f"DONE MRB {wire}#500 PASS https://example.test/pr/500",
        post_fn=lambda _p: 204,
    )
    assert r2["status"] == "duplicate"


def test_done_mrb_does_not_match_accepted_fix_same_id(tmp_path, monkeypatch):
    """FR #5095 preserved under aliasing."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _seed_roster(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [_row(PRIORITY_MCP_CANONICAL, 700, task="FIX", nick=NICK, accepted_ts="t")],
            "done": [],
        },
    )
    result = shop_listen.handle_shop_worker_line(
        tmp_path,
        nick=NICK,
        channel=SHOP,
        body=f"DONE MRB {PRIORITY_MCP_ALIAS}#700 PASS https://example.test/pr/700",
        post_fn=lambda _p: 204,
    )
    assert result["status"] == "missing"
    q = gitclaim.load_queue(tmp_path)
    acc = q.get("accepted") or []
    assert len(acc) == 1
    assert acc[0]["task"] == "FIX"
    assert acc[0]["id"] == "#700"
