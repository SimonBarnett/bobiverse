"""FR #9748: digest.copilot.tasks export (nested under pool; never machines.copilot)."""
from __future__ import annotations

import json
from pathlib import Path

import bobreport
import copilot_dispatch as cd


def test_tasks_for_digest_empty(tmp_path: Path):
    """tasks_for_digest returns empty list when no jobs file exists."""
    result = cd.tasks_for_digest(tmp_path)
    assert result == []


def test_tasks_for_digest_with_jobs(tmp_path: Path):
    """tasks_for_digest returns list of active tasks from copilot-jobs.json."""
    jobs_data = {
        "jobs": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#9748",
                "task_id": "task-123",
                "task_url": "https://github.com/SimonBarnett/bobiverse/tasks/task-123",
                "started": 1700000000.0,
                "model": "claude-haiku-4.5",
            },
            {
                "repo": "SimonBarnett/other",
                "task": "MRB",
                "id": "#42",
                "task_id": "task-456",
                "task_url": "https://github.com/SimonBarnett/other/tasks/task-456",
                "started": 1700100000.0,
            },
        ]
    }
    (tmp_path / "copilot-jobs.json").write_text(
        json.dumps(jobs_data), encoding="utf-8"
    )

    result = cd.tasks_for_digest(tmp_path)

    assert len(result) == 2
    assert result[0]["repo"] == "SimonBarnett/bobiverse"
    assert result[0]["task"] == "FR"
    assert result[0]["id"] == "#9748"
    assert result[0]["task_id"] == "task-123"
    assert result[0]["model"] == "claude-haiku-4.5"
    assert result[0]["start_model"] == "claude-haiku-4.5"
    assert result[0]["working_on"] == "FR #9748"
    assert result[1]["repo"] == "SimonBarnett/other"
    assert result[1]["task"] == "MRB"
    assert result[1]["working_on"] == "MRB #42"


def test_tasks_for_digest_malformed_file(tmp_path: Path):
    """tasks_for_digest returns empty list on file read errors."""
    (tmp_path / "copilot-jobs.json").write_text("not valid json", encoding="utf-8")
    result = cd.tasks_for_digest(tmp_path)
    assert result == []


def test_digest_copilot_tasks_nested_not_top_level(tmp_path, monkeypatch):
    """build_digest_object exposes tasks under copilot.tasks (FR #9748 shape)."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))

    (tmp_path / "copilot-allowance.json").write_text(
        json.dumps(
            {
                "enabled": True,
                "remaining": 10,
                "state": "ok",
                "unlimited": True,
                "model": "claude-haiku-4.5",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "copilot-jobs.json").write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "repo": "SimonBarnett/bobiverse",
                        "task": "FR",
                        "id": "#9748",
                        "task_id": "task-123",
                        "task_url": "https://github.com/SimonBarnett/bobiverse/tasks/task-123",
                        "started": 1700000000.0,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    bobreport.save_digest(tmp_path, bobreport.empty_digest())
    obj = bobreport.build_digest_object(tmp_path, "TestChair")

    assert "copilot_tasks" not in obj
    machines = obj.get("machines") or {}
    assert "copilot" not in machines or not isinstance(machines.get("copilot"), list)
    pool = obj.get("copilot")
    assert isinstance(pool, dict)
    tasks = pool.get("tasks")
    assert isinstance(tasks, list)
    assert len(tasks) == 1
    assert tasks[0]["repo"] == "SimonBarnett/bobiverse"
    assert tasks[0]["task"] == "FR"
    assert tasks[0]["id"] == "#9748"
    assert tasks[0]["working_on"] == "FR #9748"
    assert tasks[0]["model"] == "claude-haiku-4.5"
    assert tasks[0]["start_model"] == "claude-haiku-4.5"


def test_ensure_public_pool_keeps_tasks():
    pool = cd.ensure_public_pool({"state": "ok", "tasks": [{"repo": "o/r", "task": "FR", "id": "#1"}]})
    assert isinstance(pool.get("tasks"), list)
    assert pool["tasks"][0]["id"] == "#1"
