"""docs/mrb-5040: hostile pin for FR #5032 trayDigestTimer / weekly=0 lesson in bobiverse-bob."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob" / "SKILL.md"

NEEDLE = (
    "tray: FR #5032 trayDigestTimer Action must re-dot BobTrayDialogs"
)


def test_bobiverse_bob_pins_fr5032_tray_digest_lesson():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert NEEDLE in text
    i = text.index(NEEDLE)
    window = text[i : i + 420]
    assert all(ord(c) < 128 for c in window)
    assert "trayWorkerSyncTimer" in window
    assert "Write-BobIrcStatus" in window
    assert "weekly=0" in window
    assert "missing lastSeen" in window
    assert "[stale]" in window
    # Sits with the engine-mode FR #4142 bullet.
    assert "tray: FR #4142" in text
    assert text.index("tray: FR #4142") < i
