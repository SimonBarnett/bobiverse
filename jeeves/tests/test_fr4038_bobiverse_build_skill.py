"""FR #4038: dedicated bobiverse-build skill (read BUILD results / when to !build again)."""
from __future__ import annotations

from repo_layout import ROOT

SKILL = ROOT / "jeeves/.grok/skills/bobiverse-build/SKILL.md"
DOCS = ROOT / "docs/bobiverse-build.md"
COMMANDS = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-commands/SKILL.md"


def _utf8(p):
    raw = p.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM in {p}"
    return raw.decode("utf-8")


def test_fr4038_bobiverse_build_skill_exists_and_covers_contract():
    t = _utf8(SKILL)
    assert "name: bobiverse-build" in t
    assert "zero" in t.lower() and "token" in t.lower()
    assert "new_regression" in t and "pre_existing" in t and "flaky" in t and "step_failure" in t
    assert "dry-run" in t and "BUILD v1" in t
    assert "release-blocker" in t
    assert "When to" in t and "!build" in t
    assert "docs/bobiverse-build.md" in t
    assert "!help build" in t or "bobiverse-jeeves-commands" in t


def test_fr4038_docs_and_commands_cross_link_skill():
    docs = _utf8(DOCS)
    assert "jeeves/.grok/skills/bobiverse-build/SKILL.md" in docs
    assert "FR #4038" in docs
    cmd = _utf8(COMMANDS)
    assert "bobiverse-build" in cmd
    assert "FR #4038" in cmd
