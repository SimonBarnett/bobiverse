"""FR #7079: resolve scores multi-word seeds against skill ids, not only descriptions."""
from __future__ import annotations

from pathlib import Path

import skill_dag_mcp as mcp


def _write_skill(root: Path, name: str, description: str, depends_on: list[str] | None = None) -> None:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    deps = depends_on or []
    if deps:
        dep_block = "depends_on:\n" + "".join(f"  - {x}\n" for x in deps)
    else:
        dep_block = "depends_on: []\n"
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n{dep_block}---\n\n# {name}\n",
        encoding="utf-8",
    )


def test_fr7079_spaced_id_tokens_match_hyphen_skill_id(tmp_path: Path):
    root = tmp_path / "skills"
    _write_skill(root, "bobiverse-bob-job-irc", "Exact ACK DONE NACK wire")
    _write_skill(root, "bobiverse-bob-job-fr", "Implement one FR pull request")
    _write_skill(root, "harvest", "File intake issues")
    server = mcp.SkillDagServer(roots=[root], max_bytes=65536)
    out = server.resolve("bobiverse bob job irc")
    ids = [n["id"] for n in out["matched"]]
    assert ids, "multi-word seed must not return empty when id tokens overlap"
    assert ids[0] == "bobiverse-bob-job-irc"


def test_fr7079_exact_id_still_wins(tmp_path: Path):
    root = tmp_path / "skills"
    _write_skill(root, "bobiverse-bob-job-irc", "Exact ACK DONE NACK wire")
    server = mcp.SkillDagServer(roots=[root], max_bytes=65536)
    out = server.resolve("bobiverse-bob-job-irc")
    assert [n["id"] for n in out["matched"]][0] == "bobiverse-bob-job-irc"


def test_fr7079_unrelated_phrase_still_empty(tmp_path: Path):
    root = tmp_path / "skills"
    _write_skill(root, "bobiverse-bob-job-irc", "Exact ACK DONE NACK wire")
    server = mcp.SkillDagServer(roots=[root], max_bytes=65536)
    out = server.resolve("zzzz-no-overlap-token-qqqq")
    assert out["matched"] == []
