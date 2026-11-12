"""FR #6901: resolve scores job lines against skill descriptions."""
from __future__ import annotations

from pathlib import Path

import skill_dag_mcp as mcp

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "skill-dag"


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


def test_fr6901_description_overlap_selects_skill(tmp_path: Path):
    root = tmp_path / "skills"
    _write_skill(root, "alpha-skill", "Handles widget calibration on the bench")
    _write_skill(root, "beta-skill", "Unrelated harvest plumbing notes", depends_on=["alpha-skill"])
    server = mcp.SkillDagServer(roots=[root], max_bytes=65536)
    out = server.resolve("please run widget calibration for the fleet")
    ids = [n["id"] for n in out["matched"]]
    assert "alpha-skill" in ids
    assert ids[0] == "alpha-skill"


def test_fr6901_no_description_match_returns_empty(tmp_path: Path):
    root = tmp_path / "skills"
    _write_skill(root, "alpha-skill", "Handles widget calibration on the bench")
    server = mcp.SkillDagServer(roots=[root], max_bytes=65536)
    out = server.resolve("zzzz-no-overlap-token-qqqq")
    assert out["matched"] == []


def test_fr6901_fr_job_line_still_selects_job_fr():
    server = mcp.SkillDagServer(roots=[FIXTURES], max_bytes=65536)
    out = server.resolve("FR owner/repo#1 do the work")
    ids = [n["id"] for n in out["matched"]]
    assert "bobiverse-bob-job-fr" in ids
    assert "bobiverse-bob-job-irc" in ids


def test_fr6901_description_match_includes_depends_on(tmp_path: Path):
    root = tmp_path / "skills"
    _write_skill(root, "core-irc", "Exact ACK DONE NACK wire for worker jobs")
    _write_skill(
        root,
        "form-prep-guide",
        "Prepare Priority forms via Web SDK on DEV",
        depends_on=["core-irc"],
    )
    server = mcp.SkillDagServer(roots=[root], max_bytes=65536)
    out = server.resolve("prepare Priority forms on the DEV box")
    ids = [n["id"] for n in out["matched"]]
    assert "form-prep-guide" in ids
    assert "core-irc" in ids
    assert ids[0] == "form-prep-guide"
