# -*- coding: utf-8 -*-
"""MRB #7930: hostile pins for FR #7909 skill-root external_directory patterns."""
from __future__ import annotations

import json
from pathlib import Path

import bob_worker as bw


def test_mrb7930_redqueen_book_star_pattern(tmp_path: Path):
    """Exact form OpenCode asked for on redqueen: <skill-root>\\<book>\\*."""
    worker = tmp_path / "ai" / "bob" / "worker"
    book = worker / ".grok" / "skills" / "bobiverse-bob-job-fr"
    book.mkdir(parents=True)
    (book / "SKILL.md").write_text("# fr\n", encoding="utf-8")
    job = tmp_path / "worktree"
    cfg = bw.write_opencode_skill_dag_mcp_config(job, worker_cwd=str(worker))
    allow = json.loads(cfg.read_text(encoding="utf-8"))["permission"]["external_directory"]
    asked = str(book.resolve()) + "\\*"
    posix_asked = book.resolve().as_posix() + "/*"
    assert allow.get(asked) == "allow"
    assert allow.get(posix_asked) == "allow"
    assert allow.get(str(book.resolve()) + "\\**") == "allow"
    assert bw.opencode_skill_read_allow_gaps(cfg, str(worker)) == []


def test_mrb7930_job_write_uses_install_worker_roots(tmp_path: Path):
    """Assign path: config under job --dir, roots from install worker cwd."""
    install = tmp_path / "ai" / "bob" / "worker"
    skills = install / ".grok" / "skills" / "harvest"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text("# h\n", encoding="utf-8")
    job = tmp_path / "ai" / "worktrees" / "bobiverse" / "fr-7909"
    cfg = bw.write_opencode_skill_dag_mcp_config(
        job, worker_cwd=str(install), job_worktree=job
    )
    assert cfg == job / "opencode.json"
    allow = json.loads(cfg.read_text(encoding="utf-8"))["permission"]["external_directory"]
    assert allow.get(str(skills.resolve()) + "\\*") == "allow"
    assert str(install.resolve()) not in allow
    # Job tree may be allowed via FR #7911 when job_worktree is set.
    assert allow.get(str(job.resolve()) + "/**") == "allow"


def test_mrb7930_edit_denied_for_skill_book_glob(tmp_path: Path):
    worker = tmp_path / "worker"
    book = worker / ".grok" / "skills" / "bobiverse-bob-job-fr"
    book.mkdir(parents=True)
    cfg = bw.write_opencode_skill_dag_mcp_config(tmp_path / "wt", worker_cwd=str(worker))
    edit = json.loads(cfg.read_text(encoding="utf-8"))["permission"]["edit"]
    asked = str(book.resolve()) + "\\*"
    assert edit.get(asked) == "deny"
