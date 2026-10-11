"""docs/mrb-4141: pin engine.alive / engine_stale skill docs after FR #4136."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TROUBLE = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-troubleshooting" / "SKILL.md"
BOB = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob" / "SKILL.md"


def test_mrb4141_troubleshooting_pins_engine_stale():
    raw = TROUBLE.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf"
    t = raw.decode("utf-8")
    assert "FR #4136" in t
    assert "engine.alive" in t
    assert "engine_stale" in t
    assert "HealEngine" in t or "HealEngine" in t


def test_mrb4141_bob_skill_pins_engine_alive():
    raw = BOB.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf"
    t = raw.decode("utf-8")
    assert "FR #4136" in t
    assert "engine.alive" in t
    assert "engine_stale" in t
