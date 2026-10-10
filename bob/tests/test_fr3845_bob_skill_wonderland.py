"""FR #3845: bobiverse-bob SKILL / AGENTS / bob-ear docs include #wonderland (FR #3834)."""
from __future__ import annotations

from repo_layout import ROOT

SKILL = ROOT / "bob/.grok/skills/bobiverse-bob/SKILL.md"
AGENTS = ROOT / "bob/AGENTS.md"
EAR = ROOT / "bob/docs/bob-ear.md"
POST = ROOT / "common/docs/post-install.md"
START = ROOT / "bob/scripts/Start-Bob.ps1"


def _utf8(p):
    raw = p.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM in {p}"
    return raw.decode("utf-8")


def test_bobiverse_bob_skill_channel_list_includes_wonderland():
    t = _utf8(SKILL)
    assert "--channel #bobiverse,#wonderland,#<machine>" in t
    assert "`#bobiverse` + `#wonderland` + `#<machine>`" in t
    assert "FR #3834" in t
    assert "never `#wonderland`" in t or "never #wonderland" in t
    # Stale two-channel form must not remain as the ear CLI example.
    assert "--channel #bobiverse,#<machine>" not in t


def test_agents_and_bob_ear_match_skill():
    agents = _utf8(AGENTS)
    assert "`#bobiverse` + `#wonderland` + `#<machine>`" in agents
    assert "FR #3834" in agents
    ear = _utf8(EAR)
    assert "#bobiverse,#wonderland,#<machine>" in ear
    assert "FR #3834" in ear


def test_post_install_and_start_bob_aligned():
    post = _utf8(POST)
    assert "#bobiverse,#wonderland,#<machine>" in post
    start = START.read_text(encoding="utf-8-sig")
    assert "#bobiverse,#wonderland," in start and "$shop" in start
