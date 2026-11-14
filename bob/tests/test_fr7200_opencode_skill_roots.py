"""FR #7200: generated OpenCode config allows read-only fleet skill roots."""
from __future__ import annotations

import json
from pathlib import Path

import bob_worker as bw


def _layout(tmp_path: Path) -> Path:
    """Install-shaped tree: <ai>/bob/worker and <ai>/bob/bob/.grok/skills."""
    bob = tmp_path / "bob"
    worker = bob / "worker"
    (worker / ".grok" / "skills" / "bobiverse-bob-job-fr").mkdir(parents=True)
    (worker / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md").write_text(
        "# fr\n", encoding="utf-8"
    )
    (bob / "bob" / ".grok" / "skills").mkdir(parents=True)
    return worker


def test_generated_config_allows_exactly_skill_roots_read_only(tmp_path: Path):
    worker = _layout(tmp_path)
    cfg = bw.write_opencode_skill_dag_mcp_config(worker, worker_cwd=str(worker))
    data = json.loads(cfg.read_text(encoding="utf-8"))
    perm = data.get("permission") or {}
    allow = perm.get("external_directory") or {}
    edit = perm.get("edit") or {}
    worker_skills = str((worker / ".grok" / "skills").resolve())
    bob_skills = str((worker.parent / "bob" / ".grok" / "skills").resolve())
    assert allow.get(worker_skills) == "allow"
    assert allow.get(bob_skills) == "allow"
    assert str(worker.resolve()) not in allow
    assert str(worker.parent.resolve()) not in allow
    assert edit.get(worker_skills) == "deny"
    assert edit.get(bob_skills) == "deny"
    for path in allow:
        assert path.endswith(str(Path(".grok") / "skills")) or path.replace("\\", "/").endswith(
            ".grok/skills"
        )


def test_skill_md_path_is_under_an_allowed_root(tmp_path: Path):
    worker = _layout(tmp_path)
    skill = (worker / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md").resolve()
    roots = [p.resolve() for p in bw.skill_dag_mcp_skill_roots(str(worker))]
    assert any(skill.is_relative_to(root) for root in roots)
