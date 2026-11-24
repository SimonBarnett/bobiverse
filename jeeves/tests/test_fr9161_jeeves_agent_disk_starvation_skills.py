# -*- coding: utf-8 -*-
"""FR #9161: disk-starvation skill + mrb-gate / queue-triage / monitor harvest pins."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

SKILLS = ROOT / "jeeves" / ".grok" / "skills"
DISK = SKILLS / "bobiverse-jeeves-agent-disk-starvation" / "SKILL.md"
MRB = SKILLS / "bobiverse-jeeves-agent-mrb-gate" / "SKILL.md"
QUEUE = SKILLS / "bobiverse-jeeves-agent-queue-triage" / "SKILL.md"
MONITOR = SKILLS / "bobiverse-jeeves-agent-monitor" / "SKILL.md"


def _text(p: Path) -> str:
    assert p.is_file(), p
    return p.read_text(encoding="utf-8")


def test_fr9161_disk_starvation_skill_shape():
    t = _text(DISK)
    assert t.startswith("---\n") or t.startswith("---\r\n")
    assert "name: bobiverse-jeeves-agent-disk-starvation" in t
    assert "bobiverse-jeeves-agent-monitor" in t
    assert "worktree-create-failed:disk" in t
    assert "require_machine:" in t
    assert "disk_starvation" in t
    assert "Clear-BobiverseJobWorktrees" in t or "stale job worktrees" in t.lower()
    assert "bob-bridge" in t or "Invoke-BobiverseDiskStarvationRemediate" in t
    assert "cdk.out" in t
    assert "Never" in t or "Forbidden" in t
    assert "CAST IRON RULE" in t
    # ASCII-ish: no smart quotes / em dash
    assert "\u2019" not in t
    assert "\u2014" not in t


def test_fr9161_mrb_gate_relayed_merge_rule():
    t = _text(MRB)
    assert "Relayed merge" in t or "relayed" in t.lower()
    assert "admin-merge" in t.lower() or "admin merge" in t.lower()
    assert "Si's own words" in t or "Si's own" in t
    assert "one" in t.lower() and ("fix issue" in t.lower() or "validator" in t.lower())


def test_fr9161_queue_triage_twin_pr_and_known_bugs():
    t = _text(QUEUE)
    assert "Twin-closed issue" in t or "twin-closed" in t.lower()
    assert "List for Si" in t or "list for Si" in t
    assert "9080" in t or "Held MRB" in t
    assert "Depends-on" in t or "8808" in t
    assert "bobiverse-jeeves-agent-disk-starvation" in t


def test_fr9161_monitor_links_disk_starvation():
    t = _text(MONITOR)
    assert "bobiverse-jeeves-agent-disk-starvation" in t
    assert "worktree-create-failed:disk" in t


def test_fr9161_skill_dag_edge_disk_depends_on_monitor():
    import sys

    sys.path.insert(0, str(ROOT / "bob" / "scripts"))
    import skill_dag_index as idx  # noqa: WPS433

    node = idx._node_from_skill(DISK)
    assert node is not None
    assert node["id"] == "bobiverse-jeeves-agent-disk-starvation"
    assert "bobiverse-jeeves-agent-monitor" in list(node.get("depends_on") or [])
    nodes = idx.scan_skills([SKILLS])
    by_id = {n["id"]: n for n in nodes}
    assert "bobiverse-jeeves-agent-disk-starvation" in by_id
    assert "bobiverse-jeeves-agent-monitor" in by_id
    assert idx.find_cycle(nodes) is None
