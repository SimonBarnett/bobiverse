"""FR #3304: worker skill/AGENTS note — no realistic secret literals in tests."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
AGENTS = ROOT / "agents" / "worker" / "AGENTS.md"


def _utf8_no_bom(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n") or raw.endswith(b"\r\n"), path
    return raw.decode("utf-8")


def test_fr3304_worker_skill_pins_fake_fixture_playbook():
    text = _utf8_no_bom(SKILL)
    assert "Test fixtures (FR #3304)" in text
    idx = text.index("Test fixtures (FR #3304)")
    window = text[idx : idx + 420]
    assert "fakeSecrets.js" in window
    assert "GitGuardian" in window
    assert "runtime" in window.lower()


def test_fr3304_worker_agents_pins_no_realistic_literals():
    text = _utf8_no_bom(AGENTS)
    assert "Never write realistic secret literals in tests" in text
    assert "FR #3304" in text
    assert "fakeSecrets.js" in text
