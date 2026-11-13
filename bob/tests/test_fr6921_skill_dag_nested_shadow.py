"""FR #6921: nested skill-dba books must not shadow canonical harvest-agent-skills."""
from __future__ import annotations

from pathlib import Path

import skill_dag_index as idx
import skill_dag_mcp as mcp

REPO = Path(__file__).resolve().parents[2]
COMMON_SKILLS = REPO / "common" / ".grok" / "skills"
CANONICAL = COMMON_SKILLS / "harvest-agent-skills" / "SKILL.md"


def test_fr6921_harvest_agent_skills_is_canonical_with_harvest_dep():
    assert CANONICAL.is_file()
    nodes = idx.scan_skills([COMMON_SKILLS])
    node = next(n for n in nodes if n["id"] == "harvest-agent-skills")
    assert Path(node["path"]).resolve() == CANONICAL.resolve()
    assert "harvest" in [str(d) for d in node["depends_on"]]

    server = mcp.SkillDagServer(roots=[COMMON_SKILLS])
    got = server.nodes["harvest-agent-skills"]
    assert Path(got["path"]).resolve() == CANONICAL.resolve()
    assert "harvest" in [str(d) for d in got["depends_on"]]


def test_fr6921_nested_book_is_skipped(tmp_path: Path):
    root = tmp_path / "skills"
    canon = root / "harvest-agent-skills"
    nested = root / "bobiverse-fleet-ops" / "skill-dba" / ".grok" / "skills" / "harvest-agent-skills"
    canon.mkdir(parents=True)
    nested.mkdir(parents=True)
    (canon / "SKILL.md").write_text(
        "---\nname: harvest-agent-skills\ndescription: canonical\ndepends_on:\n  - harvest\n---\n\n# canon\n",
        encoding="utf-8",
    )
    (nested / "SKILL.md").write_text(
        "---\nname: harvest-agent-skills\ndescription: nested copy\ndepends_on: []\n---\n\n# nested\n",
        encoding="utf-8",
    )
    nodes, collisions = idx.scan_skills_with_collisions([root])
    assert collisions == []
    node = next(n for n in nodes if n["id"] == "harvest-agent-skills")
    assert Path(node["path"]).resolve() == (canon / "SKILL.md").resolve()
    assert node["depends_on"] == ["harvest"]


def test_fr6921_same_name_in_vision_roots_prefers_first_root(tmp_path: Path):
    """FR #7076: harvest copies across roots are not status last_error collisions."""
    a = tmp_path / "root-a" / "dup-skill"
    b = tmp_path / "root-b" / "dup-skill"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    (a / "SKILL.md").write_text(
        "---\nname: dup-skill\ndescription: first\ndepends_on: []\n---\n\n# a\n",
        encoding="utf-8",
    )
    (b / "SKILL.md").write_text(
        "---\nname: dup-skill\ndescription: second\ndepends_on: []\n---\n\n# b\n",
        encoding="utf-8",
    )
    nodes, collisions = idx.scan_skills_with_collisions([tmp_path / "root-a", tmp_path / "root-b"])
    assert collisions == []
    ids = [n["id"] for n in nodes]
    assert ids.count("dup-skill") == 1
    node = next(n for n in nodes if n["id"] == "dup-skill")
    assert Path(node["path"]).resolve() == (a / "SKILL.md").resolve()
    server = mcp.SkillDagServer(roots=[tmp_path / "root-a", tmp_path / "root-b"])
    assert server.last_error == ""
    assert Path(server.nodes["dup-skill"]["path"]).resolve() == (a / "SKILL.md").resolve()
