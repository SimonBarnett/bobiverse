"""FR #4711: owner issue_comment after giveup_ts clears needs_human so !bored re-offers."""
from __future__ import annotations

import time
from pathlib import Path

import bobcallback
import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines as rm
import shop_listen


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rm.sync_from_chanserv(tmp_path, ["#bobiverse", "#marchhare"])
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    fi.handle_focus_cmd(tmp_path, "a-search")
    return tmp_path


def _digest_idle(home: Path, nick: str) -> None:
    mid = bobreport.parse_seat_nick(nick)[0]
    doc = bobreport.load_digest(home)
    machines = doc.setdefault("machines", {})
    machines[mid] = {
        "id": mid,
        "online": True,
        "working_on": "",
        "worker_list": [
            {
                "nick": nick,
                "state": "idle",
                "work": "",
                "updated": "2026-10-18T13:00:00Z",
            }
        ],
    }
    bobreport.save_digest(home, doc)


def _needs_human_fr(**kw):
    row = {
        "repo": "SimonBarnett/a-search",
        "task": "FR",
        "id": "#4126",
        "seq": 1,
        "ts": "2026-10-18T12:00:00Z",
        "line": "FR a-search#4126",
        "title": "FR: Awin playbook",
        "url": "https://github.com/SimonBarnett/a-search/issues/4126",
        "needs_human": True,
        "giveup_count": 2,
        "giveup_seats": "win-mpre8vi4u6u-14652,flamingo-33384",
        "giveup_ts": "2026-10-18T12:56:00Z",
        "cooldown_until": "2026-10-18T13:26:00Z",
    }
    row.update(kw)
    return row


def _issue_comment_payload(
    *,
    body: str,
    created_at: str = "2026-10-18T13:20:36Z",
    login: str = "SimonBarnett",
    association: str = "OWNER",
    number: int = 4126,
    action: str = "created",
):
    return {
        "action": action,
        "issue": {
            "number": number,
            "title": "FR: Awin playbook",
            "state": "open",
            "html_url": f"https://github.com/SimonBarnett/a-search/issues/{number}",
        },
        "comment": {
            "id": 1,
            "body": body,
            "created_at": created_at,
            "user": {"login": login},
            "author_association": association,
            "html_url": f"https://github.com/SimonBarnett/a-search/issues/{number}#issuecomment-1",
        },
        "repository": {
            "full_name": "SimonBarnett/a-search",
            "owner": {"login": "SimonBarnett"},
        },
        "sender": {"login": login},
    }


def test_owner_comment_after_giveup_ts_clears_needs_human_and_offers(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [_needs_human_fr()], "accepted": [], "done": []},
    )
    nick = "marchhare-21524"
    _digest_idle(home, nick)

    # Still blocked before owner comment.
    st0, offered0 = gitclaim.offer_focus_top(home, nick, "#marchhare", now=time.time())
    assert st0 == "empty" and offered0 is None

    cleared = gitclaim.clear_needs_human_from_owner_issue_comment(
        home,
        "issue_comment",
        _issue_comment_payload(
            body="Don't give up on this for lack of FR-061. Source is in #4123 comments."
        ),
    )
    assert cleared is True

    doc = gitclaim._load_queue_unlocked(home)
    row = doc["unaccepted"][0]
    assert not row.get("needs_human")
    assert int(row.get("giveup_count") or 0) == 0
    assert not row.get("giveup_seats")
    assert not row.get("cooldown_until")

    st, offered = gitclaim.offer_focus_top(home, nick, "#marchhare", now=time.time())
    assert st == "ok"
    assert offered["id"] == "#4126"


def test_seat_giveup_comment_leaves_needs_human(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [_needs_human_fr()], "accepted": [], "done": []},
    )
    cleared = gitclaim.clear_needs_human_from_owner_issue_comment(
        home,
        "issue_comment",
        _issue_comment_payload(
            body="GIVEUP FR SimonBarnett/a-search#4126\nreason=needs_human: blocked on Merc FR-061"
        ),
    )
    assert cleared is False
    row = gitclaim._load_queue_unlocked(home)["unaccepted"][0]
    assert row.get("needs_human") is True
    assert int(row.get("giveup_count") or 0) == 2


def test_owner_comment_before_giveup_ts_does_not_clear(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [_needs_human_fr()], "accepted": [], "done": []},
    )
    cleared = gitclaim.clear_needs_human_from_owner_issue_comment(
        home,
        "issue_comment",
        _issue_comment_payload(
            body="earlier note",
            created_at="2026-10-18T12:50:00Z",  # before giveup_ts 12:56Z
        ),
    )
    assert cleared is False
    assert gitclaim._load_queue_unlocked(home)["unaccepted"][0].get("needs_human") is True


def test_issue_comment_event_accepted_by_callback(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [_needs_human_fr()], "accepted": [], "done": []},
    )
    import json

    body = json.dumps(
        _issue_comment_payload(
            body="Unblocked: see #4123. Don't give up for lack of FR-061."
        )
    ).encode("utf-8")
    code, _ = bobcallback.handle_git_webhook(
        {"X-GitHub-Event": "issue_comment"},
        body,
        home,
    )
    assert code in (200, 204)
    row = gitclaim._load_queue_unlocked(home)["unaccepted"][0]
    assert not row.get("needs_human")


def test_non_owner_comment_does_not_clear(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [_needs_human_fr()], "accepted": [], "done": []},
    )
    cleared = gitclaim.clear_needs_human_from_owner_issue_comment(
        home,
        "issue_comment",
        _issue_comment_payload(
            body="I can help with this",
            login="random-collaborator",
            association="CONTRIBUTOR",
        ),
    )
    assert cleared is False
