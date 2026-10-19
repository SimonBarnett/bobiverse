"""docs/mrb-4835: pin TLS handshake timeout -> GIVEUP MRB (never invent verdict)."""
from __future__ import annotations

from pathlib import Path

SKILL = (
    Path(__file__).resolve().parents[1]
    / ".grok"
    / "skills"
    / "bobiverse-bob-worker"
    / "SKILL.md"
)


def test_mrb4835_tls_handshake_giveup_bullet_contiguous():
    text = SKILL.read_text(encoding="utf-8")
    needle = "TLS handshake timeout before the PR can be read"
    assert needle in text
    idx = text.index(needle)
    chunk = text[max(0, idx - 80) : idx + 220]
    assert "GIVEUP the open MRB" in chunk
    assert "done-miss" in chunk
    assert "inventing a verdict" in chunk
    assert "\ufeff" not in text[:4]
