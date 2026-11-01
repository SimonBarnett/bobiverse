"""MRB #5365 hostile pins for EXTENSION skills docs (FR #5294)."""
from __future__ import annotations
from repo_layout import ROOT

CMD = ROOT / "airc/.grok/skills/bobiverse-airc-commands/SKILL.md"
EXT_ID = "cgmpadejahkaggjpffnhaoiafbnicgpa"

def test_mrb5365_commands_extension_section_contiguous():
    # FR #5667: fill-holes prose (#5660/#5661) pushed CredMan no-password past 1800.
    t = CMD.read_text(encoding="utf-8")
    assert not CMD.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "## EXTENSION Priority web (FR #5294)" in t
    i = t.index("## EXTENSION Priority web (FR #5294)")
    chunk = t[i : i + 2200]
    assert EXT_ID in chunk
    assert "DCCLISTEN" in chunk
    assert "Priority-web-extension" in chunk
    assert "PriorityAirc/ExtensionAdmin" in chunk
    assert "never put that password on IRC" in chunk
    assert "update=off" in chunk or "UPDATE-class" in chunk

def test_mrb5365_remote_and_troubleshooting_mention_extension():
    rem = (ROOT / "airc/docs/airc-remote-control.md").read_text(encoding="utf-8")
    assert "EXTENSION" in rem and EXT_ID in rem
    ts = (ROOT / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md").read_text(encoding="utf-8")
    assert "EXTENSION" in ts and "DCCLISTEN" in ts
