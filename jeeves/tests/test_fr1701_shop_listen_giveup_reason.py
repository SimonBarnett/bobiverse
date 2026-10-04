"""FR #1701: shop-listen GIVEUP/NACK INFO line must include truncated reason=.

Chair stdout previously logged activity='' with no reason, so monitors could not
tell require_machine vs self-MRB vs skill-skip from logs alone.
"""
from __future__ import annotations

import gitclaim
import registered_machines
import shop_listen


def _accepted_fr(repo: str, n: int, nick: str):
    return {
        "repo": repo,
        "task": "FR",
        "id": f"#{n}",
        "seq": n,
        "ts": "t",
        "line": f"FR {repo}#{n}",
        "title": "FR: log GIVEUP reason",
        "body": "require_machine: ionos",
        "labels": ["feature-request", "via-intake"],
        "state": "open",
        "url": f"https://github.com/{repo}/issues/{n}",
        "nick": nick,
        "accepted_ts": "t",
    }


def _seed_roster(home, machines=("win-mpre8vi4u6u", "marchhare", "flamingo", "ionos")):
    registered_machines.save_registered(home, set(machines))


def test_parse_giveup_captures_trailing_reason():
    parsed = shop_listen.parse_shop_job_line(
        "GIVEUP FR SimonBarnett/bobiverse#1701 require_machine=ionos"
    )
    assert parsed is not None
    assert parsed.verb == "GIVEUP"
    assert parsed.id == "#1701"
    assert parsed.rest == "require_machine=ionos"
    assert parsed.title == "require_machine=ionos"


def test_truncate_giveup_reason_collapses_and_caps():
    long = "require_machine=ionos " + ("x" * 200)
    out = shop_listen.truncate_giveup_reason(long, max_len=40)
    assert len(out) <= 40
    assert "require_machine=ionos" in out
    assert shop_listen.truncate_giveup_reason("  self-MRB   hand-back  ") == "self-MRB hand-back"
    assert shop_listen.truncate_giveup_reason("") == ""


def test_handle_giveup_returns_reason(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _seed_roster(tmp_path)
    nick = "win-mpre8vi4u6u-14452"
    channel = "#win-mpre8vi4u6u"
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [_accepted_fr("SimonBarnett/bobiverse", 1701, nick)],
            "done": [],
        },
    )
    body = "GIVEUP FR SimonBarnett/bobiverse#1701 require_machine=ionos"
    assert shop_listen.is_shop_worker_nick(nick, channel)
    assert shop_listen.parse_shop_job_line(body) is not None
    result = shop_listen.handle_shop_worker_line(
        tmp_path,
        nick=nick,
        channel=channel,
        body=body,
        post_fn=lambda _payload: 204,
    )
    assert result.get("handled") is True, result
    assert result["verb"] == "GIVEUP"
    assert result["status"] == "ok"
    assert result["activity"] == ""
    assert result["reason"] == "require_machine=ionos"
    assert result["webhook"] == 204


def test_handle_giveup_empty_reason_when_no_rest(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _seed_roster(tmp_path)
    nick = "marchhare-35016"
    channel = "#marchhare"
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [_accepted_fr("SimonBarnett/bobiverse", 99, nick)],
            "done": [],
        },
    )
    result = shop_listen.handle_shop_worker_line(
        tmp_path,
        nick=nick,
        channel=channel,
        body="GIVEUP FR SimonBarnett/bobiverse#99",
        post_fn=lambda _payload: 204,
    )
    assert result["handled"] is True
    assert result["verb"] == "GIVEUP"
    assert result.get("reason") == ""


def test_format_shop_listen_info_includes_reason_for_giveup():
    line = shop_listen.format_shop_listen_info(
        {
            "verb": "GIVEUP",
            "status": "ok",
            "activity": "",
            "webhook": 204,
            "reason": "require_machine=ionos",
        },
        nick="win-mpre8vi4u6u-14452",
    )
    assert line.startswith("INFO shop-listen GIVEUP status=ok nick=win-mpre8vi4u6u-14452")
    assert "activity=''" in line
    assert "webhook=204" in line
    assert "reason='require_machine=ionos'" in line


def test_format_shop_listen_info_ack_omits_reason_field():
    line = shop_listen.format_shop_listen_info(
        {
            "verb": "ACK",
            "status": "ok",
            "activity": "bobiverse FR #1701",
            "webhook": 204,
        },
        nick="win-mpre8vi4u6u-1",
    )
    assert "reason=" not in line
    assert "activity='bobiverse FR #1701'" in line
