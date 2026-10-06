"""MRB #2825 hostile: FR #2806 nothing-queued starts nak_s; never inject; skill pin."""
from __future__ import annotations

import time
from pathlib import Path

import bob_worker as bw
from test_bob_worker_020 import wait_until
from test_fr2806_nothing_queued_starts_nak_timer import _Seat

SKILL = (
    Path(__file__).resolve().parents[1]
    / ".grok"
    / "skills"
    / "bobiverse-bob-worker"
    / "SKILL.md"
)


def _utf8_no_bom(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n"), path
    text = raw.decode("utf-8")
    for ln in text.splitlines():
        assert not ln.startswith("<<<<<<< "), path
        assert not ln.startswith("======= "), path
        assert not ln.startswith(">>>>>>> "), path
    return text


def test_mrb2825_skill_contiguous_fr2806_nak_s_never_inject():
    text = _utf8_no_bom(SKILL)
    assert "FR #2806" in text
    idx = text.index("FR #2806")
    # Long !bored paragraph; wide window so mid-token pins stay contiguous.
    window = text[max(0, idx - 200) : idx + 280]
    assert "nak_s" in window
    assert "120" in window or "nak" in window.lower()
    assert "repeat_s" in window
    assert "180" in window
    assert "FR #2554" in window or "never inject" in window.lower() or "still never injected" in window
    assert "MRB #1617" in text[max(0, idx - 350) : idx + 50]


def test_mrb2825_inbound_kind_case_and_punctuation():
    assert bw.inbound_kind("Nothing Queued", "marchhare-1") == "nak"
    assert bw.inbound_kind("marchhare-1: NOTHING QUEUED", "marchhare-1") == "nak"
    assert bw.inbound_kind("nothing queued.", "marchhare-1") == "nak"
    assert bw.inbound_kind("nothing  queued", "marchhare-1") == "nak"


def test_mrb2825_privmsg_casefold_starts_nak_not_message():
    seat = _Seat()
    seat._on_privmsg("Jeeves", "#marchhare", "marchhare-1: Nothing Queued")
    assert seat.naks == ["nak"]
    assert seat.msgs == []
    assert any("nothing queued from Jeeves" in m for m in seat.logs)


def test_mrb2825_nak_beats_repeat_s_after_idle_cycle():
    """Production win: after an idle !bored + nothing-queued, reason=nak before repeat_s."""
    sent: list = []
    e = bw.BoredEmitter(
        lambda: sent.append(time.monotonic()) or True,
        lambda m: None,
        idle_s=0.35,
        repeat_s=1.2,
        nak_s=0.45,
        harvest_hold_s=0.0,
    )
    e.start()
    e.set_ready(True)
    assert wait_until(lambda: len(sent) == 1, 1.0)  # start
    assert wait_until(lambda: len(sent) == 2, 1.5)  # idle
    assert e.sent[-1][1] == "idle"
    t = time.monotonic()
    e.nak()  # nothing-queued path
    assert wait_until(lambda: len(sent) == 3, 1.5)
    assert e.sent[-1][1] == "nak"
    assert 0.35 <= sent[-1] - t <= 0.9
    # Must beat repeat_s (1.2s) from the idle !bored.
    assert sent[-1] - sent[-2] < 1.0
    e.stop()


def test_mrb2825_relay_still_skips_when_called_directly():
    logs: list[str] = []
    injected: list[str] = []
    r = bw.Relay(log=logs.append, clock=lambda: 0.0)
    r.inject = lambda line: injected.append(line) or True  # type: ignore[method-assign]
    assert r.deliver("Jeeves", "#marchhare", "marchhare-1: nothing queued") == "skipped"
    assert injected == []
