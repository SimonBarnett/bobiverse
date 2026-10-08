"""MRB #3333 hostile: FR #3304 fake-secret fixture note stays contiguous on main."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
AGENTS = ROOT / "agents" / "worker" / "AGENTS.md"
EXISTING = ROOT / "tests" / "test_fr3304_fake_secret_fixture_note.py"


def _utf8_no_bom(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n") or raw.endswith(b"\r\n"), path
    return raw.decode("utf-8")


def test_mrb3333_skill_fr3304_bullet_contiguous():
    text = _utf8_no_bom(SKILL)
    assert "Test fixtures (FR #3304)" in text
    idx = text.index("Test fixtures (FR #3304)")
    window = text[idx : idx + 480]
    for needle in (
        "never write realistic secret literals",
        "fakeSecrets.js",
        "GitGuardian",
        "runtime",
        "FAKE_",
        "EXAMPLE",
    ):
        assert needle in window, needle
    # bullet must remain one contiguous markdown list item (no orphan next line)
    rest = text[idx:]
    first_nl = rest.index("\n")
    bullet = rest[:first_nl]
    assert bullet.lstrip().startswith("* **Test fixtures (FR #3304):**")
    assert "force-push" in bullet or "force-pushing" in bullet


def test_mrb3333_agents_hard_rule_contiguous():
    text = _utf8_no_bom(AGENTS)
    assert "Never write realistic secret literals in tests" in text
    idx = text.index("Never write realistic secret literals in tests")
    window = text[idx : idx + 280]
    assert "FR #3304" in window
    assert "fakeSecrets.js" in window
    line = text[idx:].splitlines()[0]
    assert line.lstrip().startswith("- Never write realistic secret literals in tests")


def test_mrb3333_product_pin_module_present():
    assert EXISTING.is_file()
    src = _utf8_no_bom(EXISTING)
    assert "test_fr3304_worker_skill_pins_fake_fixture_playbook" in src
    assert "test_fr3304_worker_agents_pins_no_realistic_literals" in src
