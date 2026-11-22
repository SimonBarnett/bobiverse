"""FR #8937: no-terminal-reply keeps the open FR queued with a cooldown."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "common" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import gitclaim  # noqa: E402
import shop_listen  # noqa: E402


def test_no_terminal_reply_keeps_unaccepted_with_seat_and_cooldown(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [
                {
                    "repo": "SimonBarnett/skills-visionary",
                    "task": "FR",
                    "id": "#141",
                    "state": "open",
                    "nick": "marchhare-4208",
                    "seq": 1,
                    "ts": "2026-11-22T06:50:00Z",
                    "line": "FR SimonBarnett/skills-visionary#141",
                }
            ],
            "done": [],
        },
    )
    now = time.time()
    st, job = shop_listen.return_job_to_unaccepted(
        tmp_path,
        repo="SimonBarnett/skills-visionary",
        task="FR",
        ident="#141",
        now=now,
        reason="no-terminal-reply",
    )
    assert st == "ok" and job is not None
    assert "marchhare-4208" in str(job.get("giveup_seats") or "")
    assert job.get("cooldown_until")
    stamps = job.get("deterministic_nack_until") or {}
    assert "marchhare-4208" in stamps
    assert job.get("needs_human") is not True
    doc = gitclaim._load_queue_unlocked(tmp_path)
    assert doc.get("accepted") == []
    assert doc.get("done") in ([], None) or doc.get("done") == []
    ids = [r.get("id") for r in doc.get("unaccepted") or []]
    assert ids == ["#141"]
    # The giving seat is cooled. Another seat can take the row after the seat cooldown
    # only when the row cooldown allows it. Row cooldown blocks every seat until it ends,
    # then the giver stays in giveup_seats.
    later = now + float(gitclaim.GIVEUP_COOLDOWN_S) + 5
    st_same, same = gitclaim.offer_focus_top(
        tmp_path, "marchhare-4208", "#marchhare", now=later
    )
    assert st_same == "empty" and same is None
    st_other, offered = gitclaim.offer_focus_top(
        tmp_path, "marchhare-25376", "#marchhare", now=later
    )
    assert st_other == "ok" and offered["id"] == "#141"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
