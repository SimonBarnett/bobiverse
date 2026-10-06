"""MRB #2832 hostile: FR #2811 giveup offer + hold-until-turn-end pins."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw

WORKER_SKILL = (
    Path(__file__).resolve().parents[1]
    / ".grok"
    / "skills"
    / "bobiverse-bob-worker"
    / "SKILL.md"
)
IRC_SKILL = (
    Path(__file__).resolve().parents[1]
    / ".grok"
    / "skills"
    / "bobiverse-bob-job-irc"
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


def test_mrb2832_worker_skill_contiguous_fr2811():
    text = _utf8_no_bom(WORKER_SKILL)
    assert "FR #2811" in text
    # Prefer the !bored paragraph pin (second mention is a short harvested-lessons bullet).
    idx = text.index("**FR #2811:** while the harvest hold")
    window = text[max(0, idx - 120) : idx + 520]
    assert "held_until_turn_end" in window
    assert "turn_ended" in window
    assert "post_bored" in window
    assert "harvest hold" in window.lower() or "harvest_hold" in window


def test_mrb2832_job_irc_skill_contiguous_fr2811():
    text = _utf8_no_bom(IRC_SKILL)
    assert "FR #2811" in text
    idx = text.index("FR #2811")
    window = text[max(0, idx - 40) : idx + 380]
    assert "offer_focus_top" in window or "push" in window.lower()
    assert "nothing queued" in window.lower()
    assert "turn_ended" in window or "2802" in window


def test_mrb2832_nothing_queued_still_skipped_while_holding():
    """NQ path must run before hold-assign so FR #2554 stays intact during harvest hold."""
    logs: list[str] = []
    injected: list[str] = []
    r = bw.Relay(log=logs.append, clock=lambda: 0.0)
    r.inject = lambda line: injected.append(line) or True  # type: ignore[method-assign]
    r.hold_assigns_while = lambda: True
    assert r.deliver("Jeeves", "#marchhare", "marchhare-1: nothing queued") == "skipped"
    assert injected == []
    assert any("skipped nothing-queued" in m for m in logs)


def test_mrb2832_gitclaim_offer_after_giveup_source_pins():
    src = Path(__file__).resolve().parents[2] / "common" / "scripts" / "gitclaim.py"
    text = src.read_text(encoding="utf-8")
    assert "def offer_after_giveup" in text
    i = text.index("def offer_after_giveup")
    chunk = text[i : i + 900]
    assert 'offered_via="giveup"' in chunk or "offered_via=\"giveup\"" in chunk
    assert "offer_focus_top" in chunk
    assert "GIVEUP_OFFER_EXTRA_S" in text
