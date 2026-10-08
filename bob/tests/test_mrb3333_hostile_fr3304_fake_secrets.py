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
    lines = text.splitlines()
    matches = [ln for ln in lines if "Test fixtures (FR #3304)" in ln]
    assert len(matches) == 1, matches
    bullet = matches[0]
    assert bullet.lstrip().startswith("* **Test fixtures (FR #3304):**")
    for needle in (
        "never write realistic secret literals",
        "fakeSecrets.js",
        "GitGuardian",
        "runtime",
        "FAKE_",
        "EXAMPLE",
        "force-push",
    ):
        assert needle in bullet, needle


def test_mrb3333_agents_hard_rule_contiguous():
    text = _utf8_no_bom(AGENTS)
    lines = text.splitlines()
    matches = [
        ln for ln in lines if "Never write realistic secret literals in tests" in ln
    ]
    assert len(matches) == 1, matches
    line = matches[0]
    assert line.lstrip().startswith("- Never write realistic secret literals in tests")
    assert "FR #3304" in line
    assert "fakeSecrets.js" in line


def test_mrb3333_product_pin_module_present():
    assert EXISTING.is_file()
    src = _utf8_no_bom(EXISTING)
    assert "test_fr3304_worker_skill_pins_fake_fixture_playbook" in src
    assert "test_fr3304_worker_agents_pins_no_realistic_literals" in src
