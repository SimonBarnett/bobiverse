"""FR #7182: idle ready seats get a new FR within one offer tick; skips are logged."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines as rm


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("USERNAME", "SYSTEM")
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "systemprofile"))
    (tmp_path / "systemprofile").mkdir(exist_ok=True)
    rm.sync_from_chanserv(tmp_path, ["#bobiverse", "#redqueen", "#marchhare"])
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    fi.handle_focus_cmd(tmp_path, "bobiverse")
    return tmp_path


def _put_idle(home: Path, nick: str) -> None:
    parsed = bobreport.parse_seat_nick(nick)
    assert parsed
    mid, _pid = parsed
    doc = bobreport.load_digest(home)
    machines = doc.setdefault("machines", {})
    ent = machines.setdefault(mid, {"id": mid, "online": True})
    ent["online"] = True
    ent["worker_list"] = [
        {
            "nick": nick,
            "state": "idle",
            "work": "",
            "updated": "2026-11-14T13:06:36Z",
        }
    ]
    ent["working_on"] = ""
    bobreport.save_digest(home, doc)


def _fr_row(num=7179, repo="SimonBarnett/bobiverse"):
    return {
        "repo": repo,
        "task": "FR",
        "id": f"#{num}",
        "seq": 1,
        "ts": "2026-11-14T13:10:50Z",
        "line": "GIT issues opened",
        "url": f"https://github.com/{repo}/issues/{num}",
        "title": f"fr {num}",
        "labels": ["feature-request"],
    }


def test_fr7182_digest_idle_ready_gets_offer_without_nothing_queued(home):
    """Ready on digest, never told nothing queued: still offered within one tick."""
    said = []
    nick = "redqueen-8380"
    _put_idle(home, nick)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [_fr_row()], "accepted": [], "done": []},
    )
    gitclaim.note_worker_activity(home, nick, 1.0)
    n = gitclaim.offer_to_idle_seats(
        home, say=lambda ch, t: said.append((ch, t)) or True, now=10_000.0
    )
    assert n == 1
    assert said
    ch, line = said[0]
    assert ch.lower() == "#redqueen"
    assert line.startswith("redqueen-8380: FR SimonBarnett/bobiverse#7179")
    row = gitclaim.load_queue(home)["unaccepted"][0]
    assert "redqueen-8380" in str(row.get("offered_to") or "").lower()


def test_fr7182_focus_skip_reason_logged_per_job(home):
    said = []
    nick = "redqueen-8380"
    _put_idle(home, nick)
    fi.handle_unfocus_cmd(home, "all")
    fi.handle_focus_cmd(home, "strict on")
    fi.handle_focus_cmd(home, "SimonBarnett/not-this")
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [_fr_row()], "accepted": [], "done": []},
    )
    n = gitclaim.offer_to_idle_seats(
        home, say=lambda ch, t: said.append((ch, t)) or True, now=10_000.0
    )
    assert n == 0
    assert said == []
    stats = gitclaim.summarize_empty_offer(home, nick)
    assert stats.get("offerable") == 0
    skips = stats.get("skips") or []
    assert skips
    assert any(
        "7179" in str(s.get("key") or "") and s.get("reason") == "focus" for s in skips
    )
    detail = gitclaim.format_empty_offer_detail(nick, stats)
    assert "7179" in detail
    assert "focus" in detail.lower()


def test_fr7182_docs_pin():
    from repo_layout import ROOT

    docs = (ROOT / "jeeves" / "docs" / "empty-offer-operator.md").read_text(encoding="utf-8")
    assert "FR #7182" in docs
    skill = (ROOT / "common" / "scripts" / "gitclaim.py").read_text(encoding="utf-8")
    assert "digest_idle_ready_seats" in skill
    assert "USERNAME" not in os.environ.get("BOB_TEST_SECRET", "")
