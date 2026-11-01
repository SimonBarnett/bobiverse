"""MRB #5387 hostile pins for LEGION skills docs (FR #5312)."""
from __future__ import annotations
from repo_layout import ROOT
CMD = ROOT / "airc/.grok/skills/bobiverse-airc-commands/SKILL.md"

def test_mrb5387_legion_section_contiguous():
    t = CMD.read_text(encoding="utf-8")
    # FR #5758 extends the heading with / #5758; keep the FR #5312 anchor.
    assert "## LEGION remote install (FR #5312" in t
    i = t.index("## LEGION remote install (FR #5312")
    chunk = t[i : i + 1400]
    assert "LEGION" in chunk and "DCCLISTEN" in chunk
    assert "PriorityAirc/LegionAdmin" in chunk
    assert "update=off" in chunk or "update-disabled" in chunk
    assert "password=" not in chunk.lower()
    assert "-Profile" in chunk or "5758" in chunk or "profile_before" in chunk

def test_mrb5387_remote_and_ops_mention_legion():
    rem = (ROOT / "airc/docs/airc-remote-control.md").read_text(encoding="utf-8")
    assert "LEGION" in rem and "FR #5312" in rem
    ops = (ROOT / "airc/docs/airc-ops.md").read_text(encoding="utf-8")
    assert "LEGION" in ops
