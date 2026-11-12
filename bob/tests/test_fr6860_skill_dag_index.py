"""FR #6860: durable slim skill-dag index builder (S1, S3, S8)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

import skill_dag_index as idx

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "skill-dag"


def _write_skill(dir_path: Path, name: str, description: str, depends_on: list[str] | None = None) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    deps = depends_on or []
    if deps:
        dep_lines = "depends_on:\n" + "".join(f"  - {d}\n" for d in deps)
    else:
        dep_lines = "depends_on: []\n"
    text = (
        f"---\nname: {name}\ndescription: {description}\n{dep_lines}---\n\n"
        f"# {name}\nbody for {name}\n"
    )
    path = dir_path / "SKILL.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_s1_fixture_root_node_count_equals_skill_md_count(tmp_path: Path):
    """S1: index node count equals SKILL.md count under the fixture root."""
    root = tmp_path / "skills"
    _write_skill(root / "alpha", "alpha", "Alpha skill")
    _write_skill(root / "beta", "beta", "Beta skill", depends_on=["alpha"])
    _write_skill(root / "gamma", "gamma", "Gamma skill")
    skill_count = len(list(root.rglob("SKILL.md")))
    assert skill_count == 3

    out = tmp_path / "index.json"
    code = idx.build_index(roots=[root], index_path=out)
    assert code == 0
    assert out.is_file()
    data = idx.load_index(out)
    nodes = data["nodes"]
    assert len(nodes) == skill_count
    for node in nodes:
        assert set(node.keys()) >= {"id", "description", "depends_on", "path", "bytes"}
        assert "body" not in node
    ids = {n["id"] for n in nodes}
    assert ids == {"alpha", "beta", "gamma"}
    beta = next(n for n in nodes if n["id"] == "beta")
    assert beta["depends_on"] == ["alpha"]


def test_s1_packaged_fixtures_also_count():
    """S1 sanity: packaged skill-dag fixtures index without bodies."""
    skill_count = len(list(FIXTURES.rglob("SKILL.md")))
    assert skill_count >= 3
    # build into a sibling temp via load path through build_index
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "index.json"
        code = idx.build_index(roots=[FIXTURES], index_path=out)
        assert code == 0
        data = idx.load_index(out)
        assert len(data["nodes"]) == skill_count
        assert all("body" not in n for n in data["nodes"])


def test_s3_cycle_exits_1_previous_index_unchanged(tmp_path: Path):
    """S3: a cycle exits 1 and the previous index file bytes are unchanged."""
    root = tmp_path / "skills"
    _write_skill(root / "a", "skill-a", "A", depends_on=["skill-b"])
    _write_skill(root / "b", "skill-b", "B", depends_on=[])  # acyclic first
    out = tmp_path / "index.json"
    code = idx.build_index(roots=[root], index_path=out)
    assert code == 0
    before = out.read_bytes()
    assert before

    # Introduce a cycle: b -> a, a -> b
    _write_skill(root / "b", "skill-b", "B", depends_on=["skill-a"])
    # Ensure SKILL mtime is newer than index
    time.sleep(0.05)
    os.utime(root / "b" / "SKILL.md", None)

    code2 = idx.build_index(roots=[root], index_path=out)
    assert code2 == 1
    after = out.read_bytes()
    assert after == before


def test_s8_description_edit_rebuilds_index(tmp_path: Path):
    """S8: after a description edit, the next read of the index shows the new line."""
    root = tmp_path / "skills"
    skill = _write_skill(root / "edit-me", "edit-me", "old description line")
    out = tmp_path / "index.json"
    assert idx.build_index(roots=[root], index_path=out) == 0
    first = idx.load_index(out)
    node = next(n for n in first["nodes"] if n["id"] == "edit-me")
    assert node["description"] == "old description line"

    time.sleep(0.05)
    _write_skill(root / "edit-me", "edit-me", "new description line")
    os.utime(skill, None)

    assert idx.needs_rebuild(index_path=out, roots=[root]) is True
    assert idx.build_index(roots=[root], index_path=out) == 0
    second = idx.load_index(out)
    node2 = next(n for n in second["nodes"] if n["id"] == "edit-me")
    assert node2["description"] == "new description line"


def test_needs_rebuild_false_when_index_fresh(tmp_path: Path):
    root = tmp_path / "skills"
    _write_skill(root / "x", "x", "X")
    out = tmp_path / "index.json"
    assert idx.build_index(roots=[root], index_path=out) == 0
    # Bump index mtime ahead of sources
    future = time.time() + 5
    os.utime(out, (future, future))
    assert idx.needs_rebuild(index_path=out, roots=[root]) is False


def test_cli_main_cycle_exit_code(tmp_path: Path):
    root = tmp_path / "skills"
    _write_skill(root / "a", "a", "A", depends_on=["b"])
    _write_skill(root / "b", "b", "B", depends_on=["a"])
    out = tmp_path / "index.json"
    # Seed a good prior index manually so cycle must leave it
    prior = {
        "built_at": "2020-01-01T00:00:00Z",
        "nodes": [{"id": "seed", "description": "seed", "depends_on": [], "path": "x", "bytes": 1}],
    }
    out.write_text(json.dumps(prior), encoding="utf-8")
    before = out.read_bytes()
    # Force so the cycle check runs even though the seed index is newer than sources.
    code = idx.main(["--root", str(root), "--out", str(out), "--force"])
    assert code == 1
    assert out.read_bytes() == before
