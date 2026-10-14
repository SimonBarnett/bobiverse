"""MRB #4193 hostile pins for FR #4180 out-of-fuel ack-miss / HangDetector hold.

Contiguous needles so a mid-function splice cannot drop refuse/NACK/suppress paths
while unit tests stay green. Pins skill + bob_worker.py together.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER_PY = ROOT / "scripts" / "bob_worker.py"
SKILL = ROOT / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_hostile_skill_fr4180_contiguous_hold_rules():
    text = _read(SKILL)
    assert "while the seat is in the out-of-fuel hold, HangDetector and ack-miss must not recycle or respawn" in text
    assert "ack-miss / HangDetector must not remind, recycle, or respawn a NEW agent" in text
    assert "NACK … out-of-fuel" in text or "NACK ... out-of-fuel" in text
    assert "hang-restart counter is monotonic per incident" in text
    assert "unknown/failed fuel readings still do not count as exhausted (FR #3923)" in text
    assert "ack-miss: suppressed (out-of-fuel" in text
    assert "HUNG (...) ignored - out-of-fuel hold" in text


def test_hostile_bob_worker_fr4180_refuse_and_suppress_needles():
    src = _read(WORKER_PY)
    assert "def out_of_fuel_nack_line(" in src
    assert 'return f"NACK {key} out-of-fuel"' in src
    assert "self.refuse_assign_while" in src
    assert "self.on_refuse_assign" in src
    # Keep-both with FR #4115 outbox ACK/NACK path.
    assert "self.write_outbox" in src
    assert "skip HangDetector + ack-miss entirely" in src
    assert 'self.log("ack-miss: suppressed (out-of-fuel hold; no remind/recycle)")' in src
    assert "ignored - out-of-fuel hold (no respawn; FR #4180)" in src
    assert "restart counter is monotonic per incident" in src
    assert "relay.refuse_assign_while = lambda: bool(self.bored and self.bored.out_of_fuel)" in src
    assert "relay.on_refuse_assign = self._nack_assign_out_of_fuel" in src


def test_hostile_keep_both_write_outbox_and_refuse_assign():
    """CONFLICTING keep-both: refuse_assign (FR #4180) and write_outbox (FR #4115) coexist."""
    src = _read(WORKER_PY)
    # Both Relay attributes must remain after behind-main merges.
    idx_refuse = src.index("self.refuse_assign_while")
    idx_write = src.index("self.write_outbox")
    assert idx_refuse > 0 and idx_write > 0
    assert "FR #4180" in src[idx_refuse - 120 : idx_refuse + 80]
    assert "FR #4115" in src[idx_write - 120 : idx_write + 80]
