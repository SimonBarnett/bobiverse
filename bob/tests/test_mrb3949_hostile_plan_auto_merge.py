"""Hostile MRB #3949: plan auto-merge playbook (FR #3948).

FR #8833: plan-enable-prs / plan-git-from-plan / plan-create-repo live in
skills-visionary. Bobiverse keeps the pointer README only.
"""
from __future__ import annotations

from repo_layout import ROOT

README = ROOT / "bob/agents/plan/README.md"


def test_mrb3949_plan_source_removed_pointer_readme():
    assert README.is_file()
    text = README.read_text(encoding="utf-8")
    assert "skills-visionary" in text
    assert "releases/latest" in text
    plan = ROOT / "bob/agents/plan"
    assert not (plan / ".grok" / "skills" / "plan-enable-prs").exists()
    assert not (plan / ".grok" / "skills" / "plan-git-from-plan").exists()
    assert not (plan / ".grok" / "skills" / "plan-create-repo").exists()
