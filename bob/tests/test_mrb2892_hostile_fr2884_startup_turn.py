"""MRB #2892 hostile pins for FR #2884 startup turn_ended release (product PR #2892)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEAT_SKILL = (
    ROOT
    / "bob"
    / "agents"
    / "worker"
    / ".grok"
    / "skills"
    / "bobiverse-worker-seat"
    / "SKILL.md"
)
WORKER_SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
BOB_WORKER = ROOT / "bob" / "scripts" / "bob_worker.py"
VISION = ROOT / "bob" / "VISION.md"


def test_mrb2892_seat_skill_startup_turn_contiguous():
    raw = SEAT_SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "worker-seat SKILL.md must be UTF-8 without BOM"
    text = raw.decode("utf-8")
    assert text.endswith("\n")
    assert "## Startup readiness (FR #955 / #2884)" in text
    needle = (
        "holds inject and ``!bored`` until the first grok ``turn_ended`` after spawn "
        "(FR #2884; floor ``BOB_WORKER_STARTUP_MIN_S``, default 10 s)"
    )
    assert needle in text
    assert "``startup_grace_s``" in text
    assert "remains the **fallback**" in text
    assert "``!bored reason=start``" in text


def test_mrb2892_worker_skill_digest_mentions_2884():
    raw = WORKER_SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert text.endswith("\n")
    assert "first grok `turn_ended` after spawn (FR #2884" in text
    assert "`startup_grace_s` fallback" in text
    assert "`startup_min_s` floor" in text


def test_mrb2892_bob_worker_watcher_wires_startup_release():
    raw = BOB_WORKER.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "def _maybe_ready_on_first_turn_ended(" in text
    assert "def _note_startup_turn_started(" in text
    assert "def _ready_now(" in text
    assert 'BOB_WORKER_STARTUP_MIN_S"' in text or "BOB_WORKER_STARTUP_MIN_S" in text
    # Watcher on_ended must call the startup release helper (not only BoredEmitter.turn_ended).
    assert "self._maybe_ready_on_first_turn_ended(sid)" in text
    assert "self._note_startup_turn_started(sid)" in text
    assert 'reason="turn"' in text
    assert "first turn_ended after" in text
    assert "fallback not needed" in text


def test_mrb2892_vision_s4_still_turn_ended_bored():
    """Startup release reuses the same grok turn_ended signal family as S4 harvest hold."""
    text = VISION.read_text(encoding="utf-8")
    assert "S4" in text
    assert "turn_ended" in text
    assert "!bored" in text
