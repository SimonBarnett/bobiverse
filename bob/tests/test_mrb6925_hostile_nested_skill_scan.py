"""MRB #6925: nested-book skip is relative to the scan root, not the absolute path."""
from __future__ import annotations

from pathlib import Path

import skill_dag_index as idx


def _skill(dir_path: Path, name: str, description: str) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    path = dir_path / "SKILL.md"
    path.write_text(
        f"---\nname: {name}\ndescription: {description}\ndepends_on: []\n---\n\n# {name}\n",
        encoding="utf-8",
    )
    return path


def test_mrb6925_grok_in_root_path_does_not_skip_canonical():
    """A vision root of ``.../.grok/skills`` must still index top-level books."""
    root = Path(__file__).resolve().parents[2] / "common" / ".grok" / "skills"
    assert root.is_dir()
    skill = root / "harvest-agent-skills" / "SKILL.md"
    assert skill.is_file()
    assert idx.is_nested_skill_book(skill, root) is False
    nested = root / "bobiverse-fleet-ops" / "skill-dba" / ".grok" / "skills" / "harvest-agent-skills" / "SKILL.md"
    if nested.is_file():
        assert idx.is_nested_skill_book(nested, root) is True


def test_mrb6925_same_root_deeper_duplicate_is_collision(tmp_path: Path):
    root = tmp_path / "skills"
    shallow = _skill(root / "dup-skill", "dup-skill", "shallow")
    deep = _skill(root / "other" / "dup-skill", "dup-skill", "deep")
    nodes, collisions = idx.scan_skills_with_collisions([root])
    assert len(collisions) == 1
    assert collisions[0]["id"] == "dup-skill"
    node = next(n for n in nodes if n["id"] == "dup-skill")
    assert Path(node["path"]).resolve() == shallow.resolve()
    assert Path(node["path"]).resolve() != deep.resolve()
