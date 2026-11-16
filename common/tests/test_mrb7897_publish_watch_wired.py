"""MRB #7897: bob-ear session idle must run the publish watchdog."""
from __future__ import annotations

import inspect
from pathlib import Path

import irc_agent


def test_session_idle_calls_watch_for_bob_ear():
    src = inspect.getsource(irc_agent.Client.session)
    idle = src.split("while not self.stop.is_set() and not self.dead.wait", 1)
    assert len(idle) == 2
    assert "watch_publish_loop()" in idle[1]
    ear = irc_agent.Client.__new__(irc_agent.Client)
    ear.original_nick = "bob-marchhare"
    assert ear._seat_liveness_enabled() is False


def test_bob_ear_docs_keep_7892_and_7896():
    text = (Path(__file__).resolve().parents[2] / "bob" / "docs" / "bob-ear.md").read_text(
        encoding="utf-8"
    )
    assert "FR #7892" in text
    assert "six-hour pool window" in text
    assert "FR #7896" in text
    assert "digest-publish-loop-dead" in text
