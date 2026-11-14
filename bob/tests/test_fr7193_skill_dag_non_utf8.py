"""FR #7193: one non-UTF-8 SKILL.md must not empty the skill-dag catalog."""
from __future__ import annotations

from pathlib import Path

import skill_dag_index as idx
import skill_dag_mcp as mcp


def _utf8_skill(dir_path: Path, name: str, description: str) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    text = (
        f"---\nname: {name}\ndescription: {description}\ndepends_on: []\n---\n\n"
        f"# {name}\nbody\n"
    )
    path = dir_path / "SKILL.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_cp1252_skill_does_not_drop_utf8_neighbors(tmp_path: Path):
    root = tmp_path / "skills"
    _utf8_skill(root / "alpha", "alpha", "Alpha for MRB jobs")
    bad = root / "grok-build-fleet"
    bad.mkdir(parents=True)
    # Byte 0x97 is a cp1252 en-dash (invalid UTF-8).
    (bad / "SKILL.md").write_bytes(
        b"---\nname: grok-build-fleet\ndescription: fleet dash \x97 here\ndepends_on: []\n---\n\n# fleet\n"
    )
    out = tmp_path / "index.json"
    code = idx.build_index(roots=[root], index_path=out)
    assert code == 0
    data = idx.load_index(out)
    ids = {n["id"] for n in data["nodes"]}
    assert "alpha" in ids
    assert "grok-build-fleet" in ids
    assert data.get("status", {}).get("last_error") in ("", None) or "UnicodeDecodeError" not in str(
        data.get("status", {}).get("last_error")
    )


def test_mcp_rebuild_keeps_nodes_when_one_skill_is_cp1252(tmp_path: Path):
    root = tmp_path / "skills"
    _utf8_skill(root / "bobiverse-bob-job-mrb", "bobiverse-bob-job-mrb", "MRB hostile review")
    bad = root / "grok-build-fleet"
    bad.mkdir(parents=True)
    (bad / "SKILL.md").write_bytes(
        b"---\nname: grok-build-fleet\ndescription: dash \x97\ndepends_on: []\n---\n\n# x\n"
    )
    server = mcp.SkillDagServer(roots=[root], max_bytes=40000)
    assert "UnicodeDecodeError" not in (server.last_error or "")
    assert server.nodes
    assert "bobiverse-bob-job-mrb" in server.nodes
    out = server.resolve("MRB")
    ids = [n["id"] for n in out.get("matched") or []]
    assert "bobiverse-bob-job-mrb" in ids
    assert ids != []


def test_read_skill_markdown_replaces_invalid_utf8(tmp_path: Path):
    p = tmp_path / "SKILL.md"
    p.write_bytes(b"hello \x97 world")
    text = idx.read_skill_markdown(p)
    assert text is not None
    assert "hello" in text
    assert "world" in text
