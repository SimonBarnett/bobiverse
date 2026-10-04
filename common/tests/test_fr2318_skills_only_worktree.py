"""Harvest #2318: skills-only promote from origin/main worktree when install tip is dirty."""
from __future__ import annotations
from pathlib import Path
from repo_layout import ROOT
HAS = ROOT / "common/.grok/skills/harvest-agent-skills/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"

def test_fr2318_skills_only_worktree_playbook():
    text = HAS.read_text(encoding="utf-8")
    assert "2318" in text
    assert "origin/main" in text
    assert "skills" in text.lower() and "worktree" in text.lower()
    assert "gitclaim" in text.lower() or "dirty" in text.lower()
    assert not HAS.read_bytes().startswith(b"\xef\xbb\xbf")
    assert HAS.read_bytes().endswith(b"\n")

def test_fr2318_harvest_log():
    log = LOG.read_text(encoding="utf-8")
    assert "2318" in log
    assert "2317" in log
