"""MRB #2885 hostile pins for FR #2875 done-miss (product PR #2885)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKER_SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
BOB_WORKER = ROOT / "bob" / "scripts" / "bob_worker.py"


def test_mrb2885_skill_fr2875_done_miss_contiguous():
    raw = WORKER_SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "bobiverse-bob-worker SKILL.md must be UTF-8 without BOM"
    text = raw.decode("utf-8")
    needle = (
        "**FR #2875:** `turn_ended` with the job ACKed but no DONE/NACK/GIVEUP arms done-miss "
        "(log `done-miss armed`); after `BOB_WORKER_DONE_MISS_GRACE_S` (default 20 s) inject one "
        "bob-worker reminder (do not check the drained outbox); if the reminder turn also ends with "
        "ACK still open, clear ACK and `!bored` reason `done-miss` (never invent a DONE verdict)."
    )
    assert needle in text
    # Adjacent FR bullets remain contiguous (no orphan splice)
    assert "**FR #2834:**" in text
    assert "**FR #2811:**" in text
    assert text.index("**FR #2834:**") < text.index("**FR #2875:**") < text.index("**FR #2811:**")


def test_mrb2885_bob_worker_done_miss_symbols():
    raw = BOB_WORKER.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "def done_miss_reminder_line(" in text
    assert 'BOB_WORKER_DONE_MISS_GRACE_S"' in text or "BOB_WORKER_DONE_MISS_GRACE_S" in text
    assert 'reason == "done-miss"' in text
    assert "done-miss: still no DONE for" in text
    assert "do not check the outbox first" in text
