"""FR #8819: GET /bob/v1/models returns nested clis catalog + agents; cli read-only."""
from __future__ import annotations

import json
from pathlib import Path

import models_catalog as mc
from bobcallback import handle_request


def _write_combos(home: Path, clis: dict) -> None:
    (home / mc.MODELS_VALID_COMBOS_NAME).write_text(
        json.dumps({"version": 1, "clis": clis}, indent=2),
        encoding="utf-8",
    )


def test_fr8819_get_returns_nested_clis_and_agents(tmp_path: Path):
    """Fixture of 2 CLIs with different models → nested clis + agent rows."""
    _write_combos(
        tmp_path,
        {
            "grok": [
                {
                    "model": "grok-fixture-a",
                    "contexts": ["256", "500"],
                    "efforts": ["high", "low"],
                },
                {
                    "model": "grok-fixture-b",
                    "contexts": ["256"],
                    "efforts": ["medium"],
                },
            ],
            "cursor": [
                {
                    "model": "cursor-fixture-x",
                    "contexts": [],
                    "efforts": [],
                }
            ],
        },
    )
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
    assert "agents" in doc and "clis" in doc
    assert [r["agent"] for r in doc["agents"]] == [
        "Plan",
        "Priority",
        "Jeeves",
        "Grok",
        "Cursor",
        "Opencode",
        "Opencode-Free",
        "Copilot",
    ]
    for row in doc["agents"]:
        assert "cli" in row and row["cli"]
        assert set(row.keys()) >= {"agent", "cli", "model", "context", "effort"}

    clis = doc["clis"]
    assert set(clis.keys()) == {"Grok", "Cursor", "Opencode", "Copilot"}
    assert clis["Copilot"]["models"] == {}
    grok_models = clis["Grok"]["models"]
    assert list(grok_models.keys()) == ["grok-fixture-a", "grok-fixture-b"]
    assert grok_models["grok-fixture-a"]["contexts"]["256"]["efforts"] == [
        "high",
        "low",
    ]
    assert grok_models["grok-fixture-a"]["contexts"]["500"]["efforts"] == [
        "high",
        "low",
    ]
    assert grok_models["grok-fixture-b"]["contexts"] == {
        "256": {"efforts": ["medium"]}
    }
    # FR #9258: non-Grok rows keep the model with empty contexts (no offer).
    assert clis["Cursor"]["models"]["cursor-fixture-x"]["contexts"] == {}
    assert clis["Opencode"]["models"] == {}


def test_fr8819_cli_without_catalog_returns_empty_models_200(tmp_path: Path):
    """Missing / empty catalog → 200 with models: {} per CLI (no invent)."""
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
    clis = doc["clis"]
    assert set(clis.keys()) == {"Grok", "Cursor", "Opencode", "Copilot"}
    for name in ("Grok", "Cursor", "Opencode", "Copilot"):
        assert clis[name] == {"models": {}}


def test_fr8819_put_changing_cli_returns_4xx_unchanged(tmp_path: Path):
    """PUT that changes a row's cli is rejected; catalog file stays absent/unchanged."""
    before = list(tmp_path.iterdir())
    rows = mc.default_agent_rows()
    for row in rows:
        if row["agent"] == "Plan":
            row["cli"] = "Cursor"  # Plan is Grok — read-only
            row["model"] = "should-not-persist"
    body = json.dumps({"agents": rows}).encode("utf-8")
    code, payload = handle_request(
        "PUT",
        mc.MODELS_PATH,
        {},
        body,
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code == 400
    err = json.loads(payload.decode("utf-8"))
    assert "error" in err
    assert "cli" in err["error"].lower() or "read-only" in err["error"].lower()
    assert list(tmp_path.iterdir()) == before

    code2, payload2 = handle_request(
        "GET",
        mc.MODELS_PATH,
        {},
        b"",
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code2 == 200
    plan = next(r for r in json.loads(payload2.decode("utf-8"))["agents"] if r["agent"] == "Plan")
    assert plan["cli"] == "Grok"
    assert plan["model"] == ""


def test_fr8819_put_keeps_cli_and_accepts_selection(tmp_path: Path):
    """Valid PUT with unchanged cli persists model/context/effort; next GET shows it."""
    rows = mc.default_agent_rows()
    for row in rows:
        if row["agent"] == "Plan":
            row["model"] = "build0.1"
            row["context"] = "256"
            row["effort"] = "med"
    body = json.dumps({"agents": rows}).encode("utf-8")
    code, _ = handle_request(
        "PUT",
        mc.MODELS_PATH,
        {},
        body,
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code == 204
    code2, payload2 = handle_request(
        "GET",
        mc.MODELS_PATH,
        {},
        b"",
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code2 == 200
    doc = json.loads(payload2.decode("utf-8"))
    plan = next(r for r in doc["agents"] if r["agent"] == "Plan")
    assert plan["cli"] == "Grok"
    assert plan["model"] == "build0.1"
    assert plan["context"] == "256"
    assert plan["effort"] == "med"
    assert "clis" in doc
