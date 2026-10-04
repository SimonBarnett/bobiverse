"""MRB #2181 hostile: one-issue rule + skill consolidation once; no wrong Closes."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bob" / "scripts"))
import bob_worker


def test_mrb2181_hostile_prompt_has_one_issue_and_skill_consolidate_once():
    prompt = bob_worker.worker_prompt(r"C:\\worker", r"C:\\home", "testbox", "Bob-testbox")
    assert "One issue per issue" in prompt
    assert prompt.count("Skill-intake consolidation:") == 1
    rules = bob_worker.rules_text(r"C:\\worker", "worker")
    assert "One issue per issue" in rules
    assert rules.count("Skill-intake consolidation:") == 1


def test_mrb2181_hostile_skills_mention_close_later_twin():
    fr = (ROOT / "bob/.grok/skills/bobiverse-bob-job-fr/SKILL.md").read_text(encoding="utf-8")
    assert "One issue per issue" in fr or "one issue per issue" in fr.lower()
    assert "Harvest receipt rule" in fr
