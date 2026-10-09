"""MRB #3674 hostile pins for FR #3673 hours error hints + agent field map."""
from __future__ import annotations

import json
from pathlib import Path

import bobhours
from repo_layout import ROOT

WEBHOOKS = ROOT / "jeeves" / "docs" / "webhooks.md"
SKILL = ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves" / "SKILL.md"


def _base(**kwargs):
    body = {
        "idempotency_key": "mrb3674-k",
        "agent": "MarchHare",
        "on_behalf_of": "SimonB",
        "start": "2026-10-08T09:00:00+01:00",
        "customer": "trutex",
        "project": "deposco",
        "description": "hostile",
        "source": "cloud",
    }
    body.update(kwargs)
    return body


def test_export_user_required_hint(tmp_path: Path):
    code, payload, _ = bobhours.handle_hours_request(
        "GET", "/bob/v1/hours/export", b"", tmp_path
    )
    assert code == 400
    body = json.loads(payload)
    assert body["error"] == "user_required"
    assert body.get("hint") == "?user=USERLOGIN"


def test_handler_post_started_at_alias_is_missing_start(tmp_path: Path):
    payload = {
        "idempotency_key": "mrb3674-alias",
        "agent": "MarchHare",
        "on_behalf_of": "SimonB",
        "started_at": "2026-10-08T09:00:00+01:00",
        "customer": "trutex",
        "project": "deposco",
        "description": "hostile",
        "source": "cloud",
    }
    code, body, _ = bobhours.handle_hours_request(
        "POST", "/bob/v1/hours", json.dumps(payload).encode("utf-8"), tmp_path
    )
    assert code == 400
    err = json.loads(body)
    assert err["error"] == "missing_start"
    assert err.get("hint") == "expected: start"
    assert "started_at" in err.get("rejected_aliases", [])


def test_closed_create_returns_duration(tmp_path: Path):
    code, out = bobhours.create_entry(
        tmp_path,
        _base(
            idempotency_key="mrb3674-closed",
            end="2026-10-08T17:00:00+01:00",
        ),
    )
    assert code == 201
    assert out["status"] == "closed"
    assert out["duration_minutes"] == 480


def test_docs_contiguous_agent_field_map_and_errors():
    docs = WEBHOOKS.read_text(encoding="utf-8")
    assert "Agent field map (accepted vs rejected)" in docs
    assert "missing_start" in docs and "expected: start" in docs
    assert "user_required" in docs and "?user=USERLOGIN" in docs
    assert "`started_at`" in docs and "`customer_slug`" in docs
    assert "Create closed in one POST" in docs


def test_jeeves_skill_cites_fr3673_contiguous():
    text = SKILL.read_text(encoding="utf-8")
    assert "FR #3673" in text
    assert "missing_start" in text
    assert "jeeves/docs/webhooks.md" in text
