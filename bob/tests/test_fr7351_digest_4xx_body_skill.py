"""FR #7351: bob-worker skill FR #7181 matches FR #7347 (log scrubbed 4xx body)."""
from __future__ import annotations

from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"


def _bullet_7181(text: str) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if "**FR #7181" in line:
            chunk = [line]
            for nxt in lines[i + 1 :]:
                if nxt.startswith("- ") or nxt.startswith("## "):
                    break
                chunk.append(nxt)
            return "\n".join(chunk)
    raise AssertionError("FR #7181 bullet missing")


def test_fr7351_skill_7181_logs_scrubbed_truncated_body_not_never_body():
    text = SKILL.read_text(encoding="utf-8")
    assert "FR #7347" in text
    bullet = _bullet_7181(text)
    low = bullet.lower()
    assert "never body" not in low
    assert "200" in bullet
    assert "scrub" in low
    assert "cf-ray" in low or "CF-Ray" in bullet
