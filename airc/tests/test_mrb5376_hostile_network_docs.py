"""MRB #5376 hostile pins for NETWORK skills docs (FR #5301)."""
from __future__ import annotations
from repo_layout import ROOT
CMD = ROOT / "airc/.grok/skills/bobiverse-airc-commands/SKILL.md"

def test_mrb5376_network_section_contiguous():
    t = CMD.read_text(encoding="utf-8")
    assert "## NETWORK diagnostic (FR #5301)" in t
    i = t.index("## NETWORK diagnostic (FR #5301)")
    chunk = t[i : i + 1000]
    assert "NETWORK diag" in chunk
    assert "DCCLISTEN" in chunk
    assert "hostname" in chunk and "ips" in chunk
    assert "ou" in chunk.lower()
    assert "UPDATE-class" in chunk or "update=off" in chunk
    assert "isolated" in chunk.lower()
    assert "password=" not in chunk.lower()

def test_mrb5376_remote_table_has_network():
    rem = (ROOT / "airc/docs/airc-remote-control.md").read_text(encoding="utf-8")
    assert "NETWORK" in rem and "FR #5301" in rem
