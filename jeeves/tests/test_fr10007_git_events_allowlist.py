"""FR #10007: workflow_run and pull_request_review are accepted."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import bobcallback  # noqa: E402
import bobreport  # noqa: E402
import mrb_merge_on_green as mog  # noqa: E402


def _post(event, payload, home, monkeypatch):
    monkeypatch.setattr(bobcallback, "load_git_webhook_secret", lambda: None)
    body = json.dumps(payload).encode("utf-8")
    return bobcallback.handle_git_webhook(
        {"X-GitHub-Event": event, "X-GitHub-Delivery": "d1"},
        body,
        home,
    )


def test_fr10007_post_both_204_and_workflow_advances(tmp_path, monkeypatch):
    assert "workflow_run" in bobcallback.GIT_EVENTS
    assert "pull_request_review" in bobcallback.GIT_EVENTS
    assert "workflow_run" not in bobcallback.GIT_IGNORED_EVENTS
    repo = {"full_name": "SimonBarnett/bobiverse"}
    code, _ = _post(
        "pull_request_review",
        {"action": "submitted", "repository": repo, "review": {"state": "approved"}},
        tmp_path,
        monkeypatch,
    )
    assert code == 204
    mog.save_ledger(
        tmp_path,
        {"version": 1, "pending": [{"number": "12", "head_sha": "abc", "checks": "pending"}]},
    )
    calls = []
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: calls.append(1) or (_ for _ in ()).throw(AssertionError("rest")),
    )
    payload = {
        "repository": repo,
        "workflow_run": {
            "status": "completed",
            "conclusion": "success",
            "head_sha": "abc",
            "pull_requests": [{"number": 12}],
        },
    }
    code, _ = _post("workflow_run", payload, tmp_path, monkeypatch)
    assert code == 204
    assert bobreport.apply_git_webhook(tmp_path, "workflow_run", payload).ok
    led = mog.load_ledger(tmp_path)
    assert led["pending"][0]["checks"] == "success"
    assert led["pending"][0]["checks_source"] == "workflow_run"
    assert calls == []
    docs = (ROOT / "jeeves" / "docs" / "webhooks.md").read_text(encoding="utf-8")
    assert "workflow_run" in docs and "New-BobGitWebhook.ps1" in docs
