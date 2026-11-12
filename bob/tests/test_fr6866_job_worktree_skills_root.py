"""FR #6866: skill-dag resolve reads only the assigned job worktree skills (no sibling repo)."""
from __future__ import annotations

from pathlib import Path

import pytest

import skill_dag_mcp as mcp


def _write_skill(dir_path: Path, name: str, body: str = "body") -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    path = dir_path / "SKILL.md"
    path.write_text(
        f"---\nname: {name}\ndescription: {name}\ndepends_on: []\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return path


def test_fr6866_job_worktree_skill_returned_sibling_not_indexed(tmp_path: Path):
    job_wt = tmp_path / "job-wt"
    sibling = tmp_path / "sibling-repo"
    job_skills = job_wt / ".grok" / "skills" / "only-in-job"
    sib_skills = sibling / ".grok" / "skills" / "sibling-only"
    _write_skill(job_skills, "only-in-job", "job worktree only")
    _write_skill(sib_skills, "sibling-only", "other repo")

    roots, err = mcp.build_roots(
        base_roots=[],
        job_worktree=job_wt,
    )
    assert err == ""
    assert any(r.resolve() == (job_wt / ".grok" / "skills").resolve() for r in roots)

    server = mcp.SkillDagServer(roots=roots, max_bytes=65536)
    assert "only-in-job" in server.nodes
    assert "sibling-only" not in server.nodes
    out = server.resolve("only-in-job")
    ids = [n["id"] for n in out["matched"]]
    assert "only-in-job" in ids
    assert "sibling-only" not in ids


def test_fr6866_refuse_root_that_is_not_assigned_job_skills(tmp_path: Path):
    job_wt = tmp_path / "job-wt"
    (job_wt / ".grok" / "skills").mkdir(parents=True)
    sibling_skills = tmp_path / "other" / ".grok" / "skills"
    sibling_skills.mkdir(parents=True)

    with pytest.raises(mcp.JobSkillsRootRefused):
        mcp.accept_job_skills_root(sibling_skills, assigned_worktree=job_wt)

    ok = mcp.accept_job_skills_root(job_wt / ".grok" / "skills", assigned_worktree=job_wt)
    assert ok.resolve() == (job_wt / ".grok" / "skills").resolve()


def test_fr6866_missing_job_skills_dir_is_skipped_not_indexed(tmp_path: Path):
    job_wt = tmp_path / "empty-wt"
    job_wt.mkdir()
    roots, err = mcp.build_roots(base_roots=[], job_worktree=job_wt)
    assert err == ""
    assert roots == []
    server = mcp.SkillDagServer(roots=roots)
    assert server.nodes == {}


def test_fr6866_cli_job_worktree_adds_only_that_skills_root(tmp_path: Path, monkeypatch):
    job_wt = tmp_path / "job-wt"
    _write_skill(job_wt / ".grok" / "skills" / "cli-job", "cli-job")
    sibling = tmp_path / "sibling" / ".grok" / "skills" / "nope"
    _write_skill(sibling, "nope")

    roots = mcp.roots_from_argv(["--job-worktree", str(job_wt)])
    server = mcp.SkillDagServer(roots=roots)
    assert "cli-job" in server.nodes
    assert "nope" not in server.nodes
