"""MRB #1723: ReplyFile + console log lessons present in Airc/bob skills."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_mrb1723_airc_replyfile_skill():
    text = (ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md").read_text(encoding="utf-8")
    assert "ReplyFile" in text
    assert "airc-replies.jsonl" in text
    assert "1546" in text or "1560" in text
    assert "info_keepalive" in text or "keepalive" in text.lower()


def test_mrb1723_troubleshooting_and_commands():
    t = (ROOT / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md").read_text(encoding="utf-8")
    c = (ROOT / "bob/.grok/skills/bobiverse-bob-commands/SKILL.md").read_text(encoding="utf-8")
    assert "ReplyFile" in t and "airc-replies.jsonl" in t
    assert "airc-replies.jsonl" in c and "1546" in c


def test_mrb1723_harvest_log_and_no_markers():
    log = (ROOT / "common/docs/skill-harvest-log.md").read_text(encoding="utf-8")
    assert "#1567" in log or "1567" in log
    assert "ReplyFile" in log
    for bad in ("<<<<<<<", ">>>>>>>", "======="):
        assert bad not in log