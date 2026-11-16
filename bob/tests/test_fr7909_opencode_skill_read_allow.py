"""FR #7909: opencode.json under --dir allows read of fleet skill roots."""
from __future__ import annotations

import json
from pathlib import Path

import bob_worker as bw


def test_job_dir_config_allows_skill_book_glob(tmp_path: Path):
    worker = tmp_path / "ai" / "bob" / "worker"
    book = worker / ".grok" / "skills" / "bobiverse-bob-job-fr"
    book.mkdir(parents=True)
    (book / "SKILL.md").write_text("# fr\n", encoding="utf-8")
    job = tmp_path / "worktree"
    cfg = bw.write_opencode_skill_dag_mcp_config(job, worker_cwd=str(worker))
    assert cfg == job / "opencode.json"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    allow = data["permission"]["external_directory"]
    edit = data["permission"]["edit"]
    skill_root = (worker / ".grok" / "skills").resolve()
    asked = str(book.resolve()) + "\\*"
    assert allow.get(str(skill_root)) == "allow"
    assert allow.get(asked) == "allow"
    assert edit.get(asked) == "deny"
    assert str(worker.resolve()) not in allow
    assert str(job.resolve()) not in allow
    assert bw.opencode_skill_read_allow_gaps(cfg, str(worker)) == []


def test_missing_skill_read_allow_is_reported(tmp_path: Path, monkeypatch):
    worker = tmp_path / "worker"
    skills = worker / ".grok" / "skills"
    skills.mkdir(parents=True)
    cfg = tmp_path / "worktree" / "opencode.json"
    cfg.parent.mkdir()
    cfg.write_text("{}\n", encoding="utf-8")
    filed = []

    def _capture(component, message, *, site=""):
        filed.append(site)
        return {"ok": True}

    import runtime_failure

    monkeypatch.setattr(runtime_failure, "report_message", _capture)
    missing = bw.report_opencode_skill_read_gaps(cfg, str(worker))
    assert missing
    assert str(skills.resolve()) in missing
    assert filed == ["opencode-skill-read-allow"]
