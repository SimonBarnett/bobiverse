"""FR #7077: cross-root same skill id prefers earlier --root; not last_error."""
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


def test_fr7077_worker_root_wins_over_bob_and_user(tmp_path: Path):
    worker = tmp_path / "worker" / ".grok" / "skills"
    bob = tmp_path / "bob" / ".grok" / "skills"
    user = tmp_path / "user" / ".grok" / "skills"
    w = _skill(worker / "bobiverse-bob-job-irc", "bobiverse-bob-job-irc", "worker copy")
    _skill(bob / "bobiverse-bob-job-irc", "bobiverse-bob-job-irc", "bob copy")
    _skill(user / "bobiverse-bob-job-irc", "bobiverse-bob-job-irc", "user copy")
    roots = [worker, bob, user]
    nodes, collisions = idx.scan_skills_with_collisions(roots)
    assert collisions == []
    node = next(n for n in nodes if n["id"] == "bobiverse-bob-job-irc")
    assert Path(node["path"]).resolve() == w.resolve()
    server = mcp.SkillDagServer(roots=roots)
    assert server.last_error == ""
    assert Path(server.nodes["bobiverse-bob-job-irc"]["path"]).resolve() == w.resolve()


def test_fr7077_same_root_still_reports_collision(tmp_path: Path):
    root = tmp_path / "skills"
    shallow = _skill(root / "dup-skill", "dup-skill", "shallow")
    _skill(root / "other" / "dup-skill", "dup-skill", "deep")
    nodes, collisions = idx.scan_skills_with_collisions([root])
    assert len(collisions) == 1
    assert collisions[0]["id"] == "dup-skill"
    node = next(n for n in nodes if n["id"] == "dup-skill")
    assert Path(node["path"]).resolve() == shallow.resolve()
    server = mcp.SkillDagServer(roots=[root])
    assert "collision" in server.last_error.lower()
