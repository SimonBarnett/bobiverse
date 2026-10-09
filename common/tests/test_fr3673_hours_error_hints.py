"""FR #3673: clearer hours webhook errors (missing_start + hints) and agent field docs."""
from __future__ import annotations

import json
from pathlib import Path

import bobhours
from repo_layout import ROOT

WEBHOOKS = ROOT / "jeeves" / "docs" / "webhooks.md"


def _create_body(**kwargs):
    base = {
        "idempotency_key": "k-fr3673",
        "agent": "TrutexAgent",
        "on_behalf_of": "SimonB",
        "start": "2026-10-08T09:00:00+01:00",
        "customer": "trutex",
        "project": "deposco",
        "description": "docs",
        "source": "cloud",
    }
    base.update(kwargs)
    return base


def test_missing_start_when_field_absent(tmp_path: Path):
    body = _create_body()
    del body["start"]
    code, err = bobhours.create_entry(tmp_path, body)
    assert code == 400
    assert err["error"] == "missing_start"
    assert err.get("hint") == "expected: start"


def test_missing_start_when_started_at_alias_sent(tmp_path: Path):
    body = _create_body()
    del body["start"]
    body["started_at"] = "2026-10-08T09:00:00+01:00"
    code, err = bobhours.create_entry(tmp_path, body)
    assert code == 400
    assert err["error"] == "missing_start"
    assert err.get("hint") == "expected: start"
    assert "started_at" in err.get("rejected_aliases", [])


def test_bad_start_keeps_code_with_format_hint(tmp_path: Path):
    code, err = bobhours.create_entry(
        tmp_path, _create_body(start="not-a-date")
    )
    assert code == 400
    assert err["error"] == "bad_start"
    assert "ISO-8601" in str(err.get("hint") or "")


def test_get_list_user_required_includes_hint(tmp_path: Path):
    code, payload, _ = bobhours.handle_hours_request(
        "GET", "/bob/v1/hours", b"", tmp_path
    )
    assert code == 400
    body = json.loads(payload)
    assert body["error"] == "user_required"
    assert body.get("hint") == "?user=USERLOGIN"


def test_get_summary_user_required_includes_hint(tmp_path: Path):
    code, payload, _ = bobhours.handle_hours_request(
        "GET", "/bob/v1/hours/summary", b"", tmp_path
    )
    assert code == 400
    body = json.loads(payload)
    assert body["error"] == "user_required"
    assert "?user=" in str(body.get("hint") or "")


def test_docs_agent_field_map_and_closed_create():
    docs = WEBHOOKS.read_text(encoding="utf-8")
    assert "FR #3673" in docs or "missing_start" in docs
    assert "expected: start" in docs or "Agent field map" in docs
    assert "started_at" in docs  # rejected alias called out
    assert "customer" in docs and "project" in docs
    # closed create (start+end one POST) documented
    assert '"end"' in docs or "closed" in docs.lower()
