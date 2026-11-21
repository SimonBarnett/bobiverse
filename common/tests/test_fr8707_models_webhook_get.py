"""BOB-01 / FR #8707: GET /bob/v1/models returns fleet agent rows JSON."""
from __future__ import annotations

import json
from pathlib import Path

import models_catalog as mc
from bobcallback import handle_request


REQUIRED_AGENTS = (
    "Plan",
    "Priority",
    "Jeeves",
    "Grok",
    "Cursor",
    "Opencode",
    "Opencode-Free",
)


def test_default_agent_rows_shape():
    rows = mc.default_agent_rows()
    assert len(rows) == len(REQUIRED_AGENTS)
    names = [r["agent"] for r in rows]
    assert names == list(REQUIRED_AGENTS)
    for row in rows:
        assert set(row.keys()) == {"agent", "cli", "model", "context", "effort"}
        assert isinstance(row["cli"], str) and row["cli"]
        assert row["model"] == ""
        assert row["context"] == ""
        assert row["effort"] == ""


def test_validate_agent_row_ok_and_required():
    ok, why = mc.validate_agent_row(
        {"agent": "Plan", "cli": "Grok", "model": "x", "context": "256", "effort": "hi"}
    )
    assert why == ""
    assert ok is not None
    assert ok["agent"] == "Plan"
    assert ok["model"] == "x"

    bad, why2 = mc.validate_agent_row({"cli": "Grok"})
    assert bad is None
    assert "agent" in why2


def test_load_catalog_file_uses_defaults_when_missing(tmp_path: Path):
    rows = mc.load_catalog_file(tmp_path)
    assert [r["agent"] for r in rows] == list(REQUIRED_AGENTS)


def test_load_catalog_file_reads_valid_rows(tmp_path: Path):
    path = tmp_path / mc.MODELS_CATALOG_NAME
    path.write_text(
        json.dumps(
            {
                "agents": [
                    {
                        "agent": "Plan",
                        "cli": "Grok",
                        "model": "build0.1",
                        "context": "256",
                        "effort": "med",
                    },
                    {"agent": "", "cli": "Grok"},
                    "not-an-object",
                ]
            }
        ),
        encoding="utf-8",
    )
    rows = mc.load_catalog_file(tmp_path)
    assert len(rows) == 1
    assert rows[0]["model"] == "build0.1"


def test_catalog_to_json_compact_public_shape():
    raw = mc.catalog_to_json(mc.default_agent_rows())
    assert b" " not in raw
    doc = json.loads(raw.decode("utf-8"))
    assert isinstance(doc, dict)
    assert "agents" in doc
    assert isinstance(doc["agents"], list)
    assert len(doc["agents"]) == len(REQUIRED_AGENTS)


def test_handle_request_models_get_and_head(tmp_path: Path):
    code, payload = handle_request(
        "GET",
        mc.MODELS_PATH,
        {},
        b"",
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code == 200
    doc = json.loads(payload.decode("utf-8"))
    assert isinstance(doc.get("agents"), list)
    assert [r["agent"] for r in doc["agents"]] == list(REQUIRED_AGENTS)

    code2, payload2 = handle_request(
        "HEAD",
        mc.MODELS_PATH,
        {},
        b"",
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code2 == 200
    assert payload2 == b""


def test_handle_request_models_not_404(tmp_path: Path):
    code, payload = handle_request(
        "GET",
        "/bob/v1/models",
        {},
        b"",
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code != 404
    assert code == 200
    assert payload.startswith(b"{")


def test_example_defaults_file_validates():
    example = (
        Path(__file__).resolve().parents[1] / "defaults" / "models-catalog.example.json"
    )
    assert example.is_file()
    raw = json.loads(example.read_text(encoding="utf-8"))
    rows = raw["agents"]
    assert isinstance(rows, list) and rows
    names = []
    for item in rows:
        row, why = mc.validate_agent_row(item)
        assert row is not None, why
        names.append(row["agent"])
    assert names == list(REQUIRED_AGENTS)


def test_install_bob_webhooks_mentions_models():
    """MRB #8766: IIS front door must rewrite bob/v1/models (same class as hours)."""
    from repo_layout import ROOT

    install = (ROOT / "jeeves" / "scripts" / "Install-BobWebhooks.ps1").read_text(
        encoding="utf-8-sig"
    )
    assert "bob/v1/models" in install
    assert "BobModelsWebhook" in install
