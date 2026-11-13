"""FR #7076: same skill id across vision roots is a copy, not status last_error."""
from __future__ import annotations

from pathlib import Path

import skill_dag_index as idx
import skill_dag_mcp as mcp


def _skill(dir_path: Path, name: str, description: str) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    path = dir_path / "SKILL.md"
    path.write_text(
        f"---\nname: {name}\ndescription: {description}\ndepends_on: []\n---\n\n# {name}\n",
        encoding="utf-8",
    )
    return path


def test_fr7076_cross_root_copies_prefer_first_root_and_are_not_errors(tmp_path: Path):
    worker = tmp_path / "worker" / ".grok" / "skills"
    bob = tmp_path / "bob" / ".grok" / "skills"
    user = tmp_path / "user" / ".grok" / "skills"
    w = _skill(worker / "bobiverse-bob-job-irc", "bobiverse-bob-job-irc", "worker copy")
    _skill(bob / "bobiverse-bob-job-irc", "bobiverse-bob-job-irc", "bob copy")
    _skill(user / "bobiverse-bob-job-irc", "bobiverse-bob-job-irc", "user copy")

    nodes, collisions = idx.scan_skills_with_collisions([worker, bob, user])
    assert collisions == []
    node = next(n for n in nodes if n["id"] == "bobiverse-bob-job-irc")
    assert Path(node["path"]).resolve() == w.resolve()
    assert [n["id"] for n in nodes].count("bobiverse-bob-job-irc") == 1

    server = mcp.SkillDagServer(roots=[worker, bob, user])
    st = server.status()
    assert st["last_error"] == ""
    assert st["node_count"] == 1
    got = server.resolve("bobiverse-bob-job-irc")
    assert got["matched"][0]["path"] == str(w.resolve())


def test_fr7076_same_root_duplicate_still_collision(tmp_path: Path):
    root = tmp_path / "skills"
    _skill(root / "dup-skill", "dup-skill", "shallow")
    _skill(root / "other" / "dup-skill", "dup-skill", "deep")
    _nodes, collisions = idx.scan_skills_with_collisions([root])
    assert len(collisions) == 1
    assert collisions[0]["id"] == "dup-skill"
