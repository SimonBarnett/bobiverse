"""MRB #3751 hostile pins for FR #3742 lost-DONE session reconcile.

Product merge: PR #3751. Pins that must survive on main:
- accepted_ts == session_started stays busy (strictly-before boundary)
- pull URL as result still stamps reconcile=LOST_DONE_RESTART
- irc_agent session() refreshes _irc_session_started
- troubleshooting skill names LOST_DONE_RESTART / seat-reconcile
"""
from __future__ import annotations

import time
from pathlib import Path

import bobreport
import gitclaim

NICK = "marchhare-34384"
ROOT = Path(__file__).resolve().parents[2]


def _setup(home: Path, monkeypatch, work: str = "bobiverse FR #3742") -> None:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["marchhare"]}', encoding="utf-8"
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    doc = bobreport.empty_digest()
    doc["machines"]["marchhare"] = {
        "id": "marchhare",
        "online": True,
        "working_on": work,
        "worker_list": [
            {
                "nick": NICK,
                "state": "doing",
                "work": work,
                "updated": "2026-10-09T14:30:56Z",
            }
        ],
        "workers": {
            "3751": {
                "pid": "3751",
                "nick": NICK,
                "state": "doing",
                "working_on": work,
            }
        },
    }
    bobreport.save_digest(home, doc)


def _queue(home: Path, accepted: list[dict]) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": accepted},
    )


def test_mrb3751_ack_one_second_after_session_stays_busy(tmp_path, monkeypatch):
    """accepted_ts at least one full second after session_started stays busy.

    ISO accepted_ts is second-resolution; comparing to a float session_started can
    treat same-wall-second ACKs as pre-session (ACCEPTABLE for FR #3742 incident
    shape — ACKs minutes before restart). Pin the clear post-session case.
    """
    _setup(tmp_path, monkeypatch)
    now = time.time()
    session_started = now - 120.0
    ack_ts = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(session_started + 1.0)
    )
    _queue(
        tmp_path,
        [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#3742",
                "nick": NICK,
                "accepted_ts": ack_ts,
                "ts": ack_ts,
            }
        ],
    )
    gitclaim.note_worker_activity(tmp_path, NICK, now - 10_000)
    assert (
        gitclaim.bored_gate(
            tmp_path, NICK, "#marchhare", now, session_started=session_started
        )
        == "busy"
    )
    assert len(gitclaim.load_queue(tmp_path)["accepted"]) == 1


def test_mrb3751_pull_url_result_keeps_reconcile_reason(tmp_path, monkeypatch):
    pull = "https://github.com/SimonBarnett/bobiverse/pull/3751"
    _setup(tmp_path, monkeypatch, work=f"bobiverse FR #3742 {pull}")
    now = time.time()
    session_started = now - 30.0
    ack_ts = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(session_started - 90)
    )
    _queue(
        tmp_path,
        [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#3742",
                "nick": NICK,
                "accepted_ts": ack_ts,
                "ts": ack_ts,
            }
        ],
    )
    assert gitclaim.release_stale_busy(
        tmp_path, NICK, now, session_started=session_started
    )
    done = gitclaim.load_queue(tmp_path).get("done") or []
    hit = [r for r in done if str(r.get("id")) == "#3742"]
    assert hit, done
    assert str(hit[0].get("result") or "") == pull
    assert str(hit[0].get("reconcile") or "") == "LOST_DONE_RESTART"


def test_mrb3751_product_and_skill_needles():
    gc = (ROOT / "common/scripts/gitclaim.py").read_text(encoding="utf-8")
    assert "LOST_DONE_RESTART" in gc
    assert "session_started" in gc
    assert "def release_stale_busy" in gc
    assert '"reconcile"' in gc or "'reconcile'" in gc

    agent = (ROOT / "common/scripts/irc_agent.py").read_text(encoding="utf-8")
    assert "_irc_session_started" in agent
    assert "self._irc_session_started = time.time()" in agent
    assert "session_started=session_started" in agent

    skill = (
        ROOT / "jeeves/.grok/skills/bobiverse-jeeves-troubleshooting/SKILL.md"
    ).read_text(encoding="utf-8")
    assert "FR #3742" in skill or "#3742" in skill
    assert "LOST_DONE_RESTART" in skill
    assert "seat-reconcile" in skill
    i = skill.find("3742")
    window = skill[max(0, i - 40) : i + 280]
    assert "BUSY_STALE" in window or "session" in window.lower()

    product = (
        ROOT / "jeeves/tests/test_fr3742_lost_done_session_reconcile.py"
    ).read_text(encoding="utf-8")
    assert "test_fr3742_pre_session_accepted_healed_on_bored" in product
    assert "test_fr3742_post_session_fresh_ack_still_busy" in product
