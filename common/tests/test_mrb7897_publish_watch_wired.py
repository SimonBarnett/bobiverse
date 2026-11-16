"""MRB #7897: bob-ear session idle must run the publish watchdog."""
from __future__ import annotations

import inspect

import irc_agent


def test_session_idle_calls_watch_for_bob_ear():
    src = inspect.getsource(irc_agent.Client.session)
    idle = src.split("while not self.stop.is_set() and not self.dead.wait", 1)
    assert len(idle) == 2
    assert "watch_publish_loop()" in idle[1]
    ear = irc_agent.Client.__new__(irc_agent.Client)
    ear.original_nick = "bob-marchhare"
    assert ear._seat_liveness_enabled() is False
