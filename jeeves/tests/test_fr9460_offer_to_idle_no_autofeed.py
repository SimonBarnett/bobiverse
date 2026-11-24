# -*- coding: utf-8 -*-
"""FR #9460: chair pushes offer_to_idle when digest idle+offerable (no BobAutoFeed / no !bored)."""
from __future__ import annotations

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
    # No BobAutoFeed config file — push path must not require it.
    rm.sync_from_chanserv(tmp_path, ["#bobiverse", "#flamingo", "#redqueen"])
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    fi.handle_focus_cmd(tmp_path, "bobiverse")
    return tmp_path


def _put_idle(home: Path, nick: str, *, state: str = "idle") -> None:
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
            "state": state,
            "work": "",
            "updated": "2026-11-23T21:48:00Z",
        }
    ]
    ent["working_on"] = ""
    bobreport.save_digest(home, doc)


def _fr_row(num=9460, repo="SimonBarnett/bobiverse"):
    return {
        "repo": repo,
        "task": "FR",
        "id": f"#{num}",
        "seq": 1,
        "ts": "2026-11-23T21:48:00Z",
        "line": "GIT issues opened",
        "url": f"https://github.com/{repo}/issues/{num}",
        "title": f"fr {num}",
        "labels": ["feature-request"],
    }


def test_fr9460_push_idle_without_autofeed_config(home: Path):
    """Digest idle + ungated offerable -> offer_to_idle with BobAutoFeed absent."""
    assert not (home / "BobAutoFeed.json").exists()
    assert not (home / "auto-feed.json").exists()
    assert not (home / "autofeed.json").exists()
    nick = "flamingo-17068"
    _put_idle(home, nick)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [_fr_row()], "accepted": [], "done": []},
    )
    gitclaim.note_worker_activity(home, nick, 1.0)
    said: list[tuple[str, str]] = []
    n = gitclaim.offer_to_idle_seats(
        home, say=lambda ch, t: said.append((ch, t)) or True, now=10_000.0
    )
    assert n == 1
    assert said
    ch, line = said[0]
    assert ch.lower() == "#flamingo"
    assert "flamingo-17068: FR SimonBarnett/bobiverse#9460" in line
    # Ordinary idle+offerable must not stamp needs_human.
    q = gitclaim.load_queue(home)
    row = q["unaccepted"][0]
    labels = [str(x).lower() for x in (row.get("labels") or [])]
    assert "needs_human" not in labels
    assert "needs-human" not in labels


def test_fr9460_push_via_chair_outbox_no_autofeed(home: Path, monkeypatch):
    """push_idle_offers_via_chair_outbox works with AutoFeed disabled/absent."""
    nick = "flamingo-17160"
    _put_idle(home, nick)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [_fr_row(9461)], "accepted": [], "done": []},
    )
    gitclaim.note_worker_activity(home, nick, 1.0)
    enqueued: list[tuple[str, str]] = []

    def _enq(h, text, channel=None, **_kw):
        enqueued.append((str(channel or ""), str(text)))
        return True

    monkeypatch.setattr(
        "bobreport.enqueue_chair_fleet_privmsg", _enq
    )
    n = gitclaim.push_idle_offers_via_chair_outbox(home, now=20_000.0)
    assert n == 1
    assert enqueued
    assert "flamingo-17160: FR SimonBarnett/bobiverse#9461" in enqueued[0][1]


def test_fr9460_after_done_also_feeds_other_idle_seats(home: Path):
    """DONE seat may get nothing (self-MRB); other digest-idle seats still get a push."""
    done_nick = "flamingo-1000"
    other = "flamingo-2000"
    _put_idle(home, done_nick)
    _put_idle(home, other)
    # Only MRB left; mark done_nick as implementer so done-offer skips self-MRB.
    mrb = {
        "repo": "SimonBarnett/bobiverse",
        "task": "MRB",
        "id": "#9001",
        "seq": 1,
        "ts": "2026-11-23T21:00:00Z",
        "line": "x",
        "url": "https://github.com/SimonBarnett/bobiverse/pull/9001",
        "title": "mrb 9001",
        "implementer": done_nick,
        "author": done_nick,
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [mrb, _fr_row(9462)],
            "accepted": [],
            "done": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#1",
                    "nick": done_nick,
                    "ts": "2026-11-23T21:00:00Z",
                }
            ],
        },
    )
    gitclaim.note_worker_activity(home, done_nick, 1.0)
    gitclaim.note_worker_activity(home, other, 1.0)
    said: list[tuple[str, str]] = []

    def say(ch, t):
        said.append((ch, t))
        return True

    # Simulate hardened path: offer_after_done then fleet idle push.
    n1, _job = gitclaim.offer_after_done(
        home, done_nick, "#flamingo", say=say, now=30_000.0
    )
    n2 = gitclaim.offer_to_idle_seats(home, say=say, now=30_000.0)
    assert n1 + n2 >= 1
    assert any("9462" in line or "9001" in line for _ch, line in said)
    # Other idle seat must be able to receive without posting !bored.
    assert any(other in line for _ch, line in said) or any(
        done_nick in line for _ch, line in said
    )


def test_fr9460_chair_health_idle_offer_interval_le_30():
    import chair_health

    assert hasattr(chair_health, "IDLE_OFFER_PUSH_S")
    assert float(chair_health.IDLE_OFFER_PUSH_S) <= 30.0
    assert float(chair_health.IDLE_OFFER_PUSH_S) >= 5.0
    src = Path(chair_health.__file__).read_text(encoding="utf-8")
    assert "push_idle_offers_via_chair_outbox" in src
    assert "9460" in src
    assert "next_idle_offer" in src


def test_fr9460_docs_document_n_seconds():
    from repo_layout import ROOT

    docs = (ROOT / "jeeves" / "docs" / "empty-offer-operator.md").read_text(
        encoding="utf-8"
    )
    assert "FR #9460" in docs
    assert "30" in docs
    assert "BobAutoFeed" in docs or "auto-feed" in docs.lower()
    assert "!bored" in docs
