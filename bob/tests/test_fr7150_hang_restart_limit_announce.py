"""FR #7150: hang-restart-limit announces on shop + writes run_dir marker."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


def test_hang_restart_limit_announces_shop_and_marker(tmp_path: Path):
    clock = {"t": 0.0}
    logs: list[str] = []
    said: list[tuple[str, str]] = []
    shutdowns: list[str] = []

    class FakeProc:
        def __init__(self, pid: int):
            self.pid = pid

        def poll(self):
            return None

    class FakeIrc:
        shop = "#redqueen"

        def say(self, target: str, text: str) -> bool:
            said.append((target, text))
            return True

    class FakeRelay:
        last_unacked = None
        on_inject = None
        hold_assigns_while = None
        on_hold_assign = None
        refuse_assign_while = None
        on_refuse_assign = None

        def set_target(self, _t):
            pass

        def hold(self, _m):
            pass

    bored = bw.BoredEmitter(lambda: True, logs.append, harvest_hold_s=0.0)
    sup = bw.Supervisor(
        kind="grok",
        exe="x",
        cwd=".",
        machine="redqueen",
        nick="redqueen-916",
        run_dir=tmp_path,
        irc=FakeIrc(),
        relay=FakeRelay(),
        log=logs.append,
        clock=lambda: clock["t"],
        bored=bored,
        detector=bw.HangDetector(not_responding_s=9999, silent_s=9999),
        backoff=(0.0,),
        restart_max=3,
        restart_window_s=1800.0,
    )
    sup.start_agent = lambda note="": True  # type: ignore[method-assign]
    sup.shutdown = lambda why, code: shutdowns.append(f"{why}:{code}")  # type: ignore[method-assign]
    # kill is used on non-give-up path; stub for safety
    sup.kill = lambda pid: None  # type: ignore[method-assign]

    for i, t in enumerate((0.0, 100.0, 200.0, 300.0)):
        clock["t"] = t
        sup.proc = FakeProc(1000 + i)
        if i < 3:
            sup.restart_agent("startup-no-first-turn")
            assert not shutdowns, shutdowns
            assert said == []
        else:
            sup.restart_agent("startup-no-first-turn")

    assert shutdowns == [f"hang-restart-limit:{bw.EXIT_GAVE_UP}"]
    assert len(said) == 1
    target, text = said[0]
    assert target == "#redqueen"
    assert "hang-restart-limit" in text
    assert "reason=startup-no-first-turn" in text
    assert "restarts=3/1800s" in text
    assert f"exit={bw.EXIT_GAVE_UP}" in text
    marker = tmp_path / "hang-restart-limit.txt"
    assert marker.is_file()
    body = marker.read_text(encoding="utf-8")
    assert "hang-restart-limit" in body
    assert "startup-no-first-turn" in body
