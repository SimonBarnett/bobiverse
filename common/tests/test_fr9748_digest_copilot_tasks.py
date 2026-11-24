"""FR #9748: digest.copilot.tasks export."""
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
    # Create a jobs file with some tasks
    jobs_data = {
        "jobs": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#9748",
                "task_id": "task-123",
                "task_url": "https://github.com/SimonBarnett/bobiverse/tasks/task-123",
                "started": 1700000000.0,
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
    jobs_path = tmp_path / "copilot-jobs.json"
    jobs_path.write_text(json.dumps(jobs_data), encoding="utf-8")

    result = cd.tasks_for_digest(tmp_path)

    assert len(result) == 2
    assert result[0]["repo"] == "SimonBarnett/bobiverse"
    assert result[0]["task"] == "FR"
    assert result[0]["id"] == "#9748"
    assert result[0]["task_id"] == "task-123"
    assert result[1]["repo"] == "SimonBarnett/other"
    assert result[1]["task"] == "MRB"


def test_tasks_for_digest_malformed_file(tmp_path: Path):
    """tasks_for_digest returns empty list on file read errors."""
    # Create a malformed jobs file
    jobs_path = tmp_path / "copilot-jobs.json"
    jobs_path.write_text("not valid json", encoding="utf-8")

    result = cd.tasks_for_digest(tmp_path)
    assert result == []


def test_digest_includes_copilot_tasks(tmp_path, monkeypatch):
    """build_digest_object includes copilot_tasks from jobs file."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))

    # Create allowance file for copilot
    allowance_data = {
        "enabled": True,
        "remaining": 10,
        "state": "ok",
        "unlimited": True,
    }
    (tmp_path / "copilot-allowance.json").write_text(
        json.dumps(allowance_data), encoding="utf-8"
    )

    # Create jobs file with tasks
    jobs_data = {
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
    (tmp_path / "copilot-jobs.json").write_text(
        json.dumps(jobs_data), encoding="utf-8"
    )

    # Save and build digest
    bobreport.save_digest(tmp_path, bobreport.empty_digest())
    obj = bobreport.build_digest_object(tmp_path, "TestChair")

    # Verify copilot_tasks is in the digest
    assert "copilot_tasks" in obj
    assert isinstance(obj["copilot_tasks"], list)
    assert len(obj["copilot_tasks"]) == 1
    assert obj["copilot_tasks"][0]["repo"] == "SimonBarnett/bobiverse"
    assert obj["copilot_tasks"][0]["task"] == "FR"
    assert obj["copilot_tasks"][0]["id"] == "#9748"
