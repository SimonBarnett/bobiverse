"""Smoke: POST /bob/v1/intake + POST/GET /bob/v1/jira via handle_request."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from repo_layout import ROOT  # t773u: split repo; legacy flat paths resolve per service
sys.path.insert(0, str(ROOT / "scripts"))

import bobcallback  # noqa: E402
import intake  # noqa: E402
import jira_webhook  # noqa: E402
import webhook_queue  # noqa: E402


SECRET = "test-secret-intake-jira"
ALLOW = {"127.0.0.1"}


def _headers(**extra: str) -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    h.update(extra)
    return h


def test_intake_post_files_issue_and_announces(tmp_path: Path) -> None:
    filer = intake.FakeGitHubFiler()
    body = json.dumps(
        {
            "repo": "SimonBarnett/bobiverse",
            "title": "intake smoke",
            "body": "from test",
            # missing kind → issue
            "idempotency_key": "smoke-intake-1",
        }
    ).encode()
    code, payload = bobcallback.handle_request(
        "POST",
        "/bob/v1/intake",
        _headers(),
        body,
        "127.0.0.1",
        tmp_path,
        ALLOW,
        filer=filer,
    )
    assert code == 202
    doc = json.loads(payload.decode("utf-8"))
    assert doc.get("intake_id")
    assert doc.get("url")
    assert filer.issues and filer.issues[-1]["title"] == "intake smoke"
    pending = list((tmp_path / "webhook-queue" / "pending").glob("*.json"))
    done = list((tmp_path / "webhook-queue" / "done").glob("*.json"))
    assert not pending
    assert done
    outbox = tmp_path / "chair-outbox.txt"
    assert outbox.is_file()
    text = outbox.read_text(encoding="utf-8")
    assert "PRIVMSG #bobiverse :" in text
    assert "intake" in text.lower()

    # GET status
    iid = doc["intake_id"]
    code2, payload2 = bobcallback.handle_request(
        "GET",
        f"/bob/v1/intake/{iid}",
        {},
        b"",
        "127.0.0.1",
        tmp_path,
        ALLOW,
        filer=filer,
    )
    assert code2 == 200
    st = json.loads(payload2.decode("utf-8"))
    assert st["intake_id"] == iid
    assert st.get("url")


def test_intake_open_without_secret(tmp_path: Path) -> None:
    body = b'{"repo":"SimonBarnett/bobiverse","title":"x","body":"y","idempotency_key":"open-intake-1"}'
    code, payload = bobcallback.handle_request(
        "POST",
        "/bob/v1/intake",
        {"Content-Type": "application/json"},
        body,
        "127.0.0.1",
        tmp_path,
        ALLOW,
        filer=intake.FakeGitHubFiler(),
    )
    assert code == 202
    doc = json.loads(payload.decode("utf-8"))
    assert doc.get("intake_id")


def test_jira_post_persists_and_get_is_open(tmp_path: Path) -> None:
    payload = {
        "webhookEvent": "jira:issue_updated",
        "timestamp": 1705424400000,
        "issue": {
            "key": "PROJ-42",
            "fields": {
                "summary": "Login timeout",
                "description": "Users logged out too soon.",
                "status": {"name": "In Progress"},
                "assignee": {"displayName": "Simon Barnett"},
                "project": {"key": "PROJ"},
            },
        },
    }
    code, body = bobcallback.handle_request(
        "POST",
        "/bob/v1/jira",
        _headers(),
        json.dumps(payload).encode(),
        "127.0.0.1",
        tmp_path,
        ALLOW,
    )
    assert code == 204 and body == b""
    doc = jira_webhook.load_jira_tickets(tmp_path)
    assert "PROJ-42" in doc["tickets"]
    assert doc["tickets"]["PROJ-42"]["summary"] == "Login timeout"
    outbox = (tmp_path / "chair-outbox.txt").read_text(encoding="utf-8")
    assert "PRIVMSG #bobiverse :" in outbox
    assert "PROJ-42" in outbox
    assert list((tmp_path / "webhook-queue" / "done").glob("*.json"))

    code_ok, got = bobcallback.handle_request(
        "GET",
        "/bob/v1/jira",
        {},
        b"",
        "127.0.0.1",
        tmp_path,
        ALLOW,
    )
    assert code_ok == 200
    parsed = json.loads(got.decode("utf-8"))
    assert "PROJ-42" in parsed["tickets"]


def test_jira_post_open_without_secret(tmp_path: Path) -> None:
    code, _ = bobcallback.handle_request(
        "POST",
        "/bob/v1/jira",
        {"Content-Type": "application/json"},
        b'{"issue":{"key":"X-1","fields":{"summary":"s"}}}',
        "127.0.0.1",
        tmp_path,
        ALLOW,
    )
    assert code == 204


def test_resolve_listen_port_never_ephemeral(monkeypatch) -> None:
    monkeypatch.delenv("BOB_REPORT_PORT", raising=False)
    assert bobcallback.resolve_listen_port(0) == 7700
    assert bobcallback.resolve_listen_port(7701) == 7701
    monkeypatch.setenv("BOB_REPORT_PORT", "7705")
    assert bobcallback.resolve_listen_port(0) == 7705


def test_report_still_works_with_queue(tmp_path: Path) -> None:
    import registered_machines

    registered_machines.save_registered(tmp_path, {"win-mpre8vi4u6u"})
    body = json.dumps(
        {"op": "merge", "machine": "win-mpre8vi4u6u", "pid": 884, "working_on": "callback", "kind": "cursor"}
    ).encode()
    code, payload = bobcallback.handle_request(
        "POST",
        "/bob/v1/report",
        _headers(),
        body,
        "127.0.0.1",
        tmp_path,
        ALLOW,
    )
    assert code == 204 and payload == b""
    assert list((tmp_path / "webhook-queue" / "done").glob("*.json"))
    envs = webhook_queue.list_pending(tmp_path)
    assert envs == []
