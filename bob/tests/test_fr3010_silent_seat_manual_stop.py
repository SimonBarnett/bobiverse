"""FR #3010: bobiverse-bob-worker skill must say FR #2996 silent seats need a manual stop.

Stale-build notice (FR #2782 / #3180) only runs at post_bored / idle !bored. A seat already
stuck silent from stale _release_gen never reaches that point, so rebuild+hotpatch alone
leaves it spinning; stop the seat tree by PID and start a new seat manually (FR #3180).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"


def _text() -> str:
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), SKILL
    return raw.decode("utf-8")


def test_fr3010_skill_stale_build_notes_silent_seat():
    t = _text()
    assert "FR #3010" in t
    assert "FR #2996" in t
    assert "stale-build" in t.lower() or "stale build" in t.lower()
    assert "post_bored" in t
    assert "manual" in t.lower()
    assert "FR #3180" in t or "start a new seat manually" in t.lower()


def test_fr3010_troubleshooting_row_manual_stop():
    t = _text()
    row = [ln for ln in t.splitlines() if "`!bored` never posts" in ln]
    assert row, "missing troubleshooting row for !bored never posts"
    body = row[0]
    assert "FR #2996" in body
    assert "FR #3010" in body
    assert "stop" in body.lower()
    assert "PID" in body or "pid" in body
    assert "manual" in body.lower()
    assert "never reaches" in body.lower() or "never fires" in body.lower() or "will **not**" in body
