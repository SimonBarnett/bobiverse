"""FR #9749: dispatch POST + job record use Weights Copilot model (omit when empty)."""
from __future__ import annotations

import json
from pathlib import Path
import copilot_dispatch as cd
import models_catalog as mc

REPO = "SimonBarnett/bobiverse"


def _row(task="FR", num=9749, **extra):
    row = {
        "repo": REPO,
        "task": task,
        "id": f"#{num}",
        "url": f"https://github.com/{REPO}/issues/{num}",
        "title": "dispatch weights model",
    }
    row.update(extra)
    return row


def _write_weights_copilot(home: Path, model: str) -> None:
    rows = mc.default_agent_rows()
    for r in rows:
        if r["agent"] == "Copilot":
            r["model"] = model
    path = mc.catalog_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"agents": rows}), encoding="utf-8")


def test_fr9749_build_task_body_includes_weights_model(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_COPILOT_MODEL", raising=False)
    _write_weights_copilot(tmp_path, "claude-haiku-4.5")
    body = cd.build_task_body(_row(), home=tmp_path)
    assert body["model"] == "claude-haiku-4.5"
    assert "prompt" in body
    # No credential-shaped values in the POST body (prompt may say "Never print secrets").
    blob = json.dumps(body)
    assert "FAKE_" not in blob
    assert "ghp_" not in blob
    assert "github_pat_" not in blob
    assert "Bearer " not in blob


def test_fr9749_build_task_body_omits_model_when_weights_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_COPILOT_MODEL", "should-not-appear")
    _write_weights_copilot(tmp_path, "")
    body = cd.build_task_body(_row(), home=tmp_path)
    assert "model" not in body
    assert body.get("model", "MISSING") != ""


def test_fr9749_weights_copilot_model_helper(tmp_path):
    assert cd.weights_copilot_model(None) == ""
    assert cd.weights_copilot_model(tmp_path) == ""
    _write_weights_copilot(tmp_path, "claude-haiku-4.5")
    assert cd.weights_copilot_model(tmp_path) == "claude-haiku-4.5"


def _patch_dispatch_gates(monkeypatch):
    monkeypatch.setattr(cd, "has_allowance", lambda *a, **k: True)
    monkeypatch.setattr(cd, "is_high_priority", lambda *a, **k: True)
    monkeypatch.setattr(cd, "should_dispatch", lambda *a, **k: True)
    monkeypatch.setattr(cd.gitclaim, "ledger_blocks", lambda *a, **k: False)
    monkeypatch.setattr(cd.gitclaim, "ledger_load", lambda *a, **k: {})
    monkeypatch.setattr(
        cd.shop_listen, "accept_job_by_ref", lambda *a, **k: ("ok", {})
    )
    monkeypatch.setattr(cd, "record_api_result", lambda *a, **k: None)
    monkeypatch.setattr(cd, "is_exhausted", lambda *a, **k: False)
    monkeypatch.setattr(cd.bobreport, "enqueue_chair_fleet_privmsg", lambda *a, **k: None)
    if hasattr(cd.bobreport, "machine_id"):
        monkeypatch.setattr(cd.bobreport, "machine_id", lambda: "")


def test_fr9749_dispatch_row_persists_model_on_job(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_COPILOT_MODEL", raising=False)
    _write_weights_copilot(tmp_path, "claude-haiku-4.5")
    _patch_dispatch_gates(monkeypatch)
    seen = {}

    def _fake_post(path, body):
        seen["body"] = body
        return {
            "id": "task-9749",
            "html_url": "https://example.invalid/agents/tasks/task-9749",
        }

    out = cd.dispatch_row(tmp_path, _row(), post=_fake_post, now=1.0, announce=lambda _l: None)
    assert out["status"] == "dispatched"
    assert seen["body"].get("model") == "claude-haiku-4.5"
    jobs = cd._load_jobs(tmp_path)["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["model"] == "claude-haiku-4.5"
    assert jobs[0]["start_model"] == "claude-haiku-4.5"


def test_fr9749_dispatch_row_omits_job_model_when_weights_empty(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_COPILOT_MODEL", raising=False)
    _write_weights_copilot(tmp_path, "")
    _patch_dispatch_gates(monkeypatch)
    seen = {}

    def _fake_post(path, body):
        seen["body"] = body
        return {
            "id": "task-9749b",
            "html_url": "https://example.invalid/agents/tasks/task-9749b",
        }

    out = cd.dispatch_row(
        tmp_path, _row(num=9750), post=_fake_post, now=2.0, announce=lambda _l: None
    )
    assert out["status"] == "dispatched"
    assert "model" not in seen["body"]
    job = cd._load_jobs(tmp_path)["jobs"][0]
    assert "model" not in job
    assert "start_model" not in job
