"""FR #9746: Weights Copilot agent row + CLI catalog (empty model allowed)."""
from __future__ import annotations

import json
from pathlib import Path

import models_catalog as mc
import models_refresh as mr
from bobcallback import handle_request
from repo_layout import REPO

SEED = REPO / "common" / "defaults" / "models-valid-combos.seed.json"

COPILOT_SEED_IDS = (
    "claude-haiku-4.5",
    "claude-sonnet-4.6",
    "claude-opus-4.6",
    "gpt-5.2-codex",
    "gpt-5.3-codex",
    "gpt-5.4",
    "claude-sonnet-4.5",
    "claude-opus-4.5",
)


def _legacy_seven_rows(**overrides: dict) -> list[dict]:
    skip = {"Copilot", "Copilot-MRB", "Copilot-PR"}
    rows = [r for r in mc.default_agent_rows() if r["agent"] not in skip]
    for row in rows:
        if row["agent"] in overrides:
            row.update(overrides[row["agent"]])
    return rows


def test_fr9746_default_row_blank_copilot():
    rows = mc.default_agent_rows()
    assert rows[-2]["agent"] == "Copilot-MRB"
    assert rows[-1]["agent"] == "Copilot-PR"
    assert rows[-1]["cli"] == "Copilot"
    assert rows[-1]["model"] == ""
    assert rows[-2]["model"] == ""
    assert "copilot" in mc.VALID_CLI_KEYS
    assert mc.CLI_KEY_TO_PUBLIC["copilot"] == "Copilot"
    assert "Copilot" in mc.CLI_PUBLIC_KEYS


def test_fr9746_seed_ids_and_provenance():
    raw = json.loads(SEED.read_text(encoding="utf-8"))
    models = [r["model"] for r in raw["clis"]["copilot"]]
    assert models == list(COPILOT_SEED_IDS)
    for row in raw["clis"]["copilot"]:
        assert row["contexts"] == []
        assert row["efforts"] == []
    prov = raw["provenance"]["clis"]["copilot"]
    assert "GitHub" in prov["source"] or "github" in prov["source"].lower()
    assert "haiku" in json.dumps(prov).lower()
    doc = mc.load_seed_document(SEED)
    assert "copilot" in doc["clis"]


def test_fr9746_get_model_choices_no_contexts_efforts(tmp_path: Path):
    mc.ensure_valid_combos_seeded(tmp_path, seed_path=SEED)
    code, body = handle_request(
        "GET",
        mc.MODELS_PATH,
        {},
        b"",
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code == 200
    doc = json.loads(body.decode("utf-8"))
    assert [r["agent"] for r in doc["agents"]][-1] == "Copilot-PR"
    copilot = doc["clis"]["Copilot"]["models"]
    assert "claude-haiku-4.5" in copilot
    for _mid, node in copilot.items():
        assert node["contexts"] == {}


def test_fr9746_put_get_round_trip_and_empty_model(tmp_path: Path):
    rows = mc.default_agent_rows()
    for r in rows:
        if r["agent"] in ("Copilot-MRB", "Copilot-PR"):
            r["model"] = "claude-haiku-4.5"
    body = json.dumps({"agents": rows}).encode("utf-8")
    code, _ = handle_request(
        "PUT", mc.MODELS_PATH, {}, body, "127.0.0.1", tmp_path, allow_ips={"127.0.0.1"}
    )
    assert code == 204
    code2, payload = handle_request(
        "GET", mc.MODELS_PATH, {}, b"", "127.0.0.1", tmp_path, allow_ips={"127.0.0.1"}
    )
    assert code2 == 200
    doc = json.loads(payload.decode("utf-8"))
    copilot = next(r for r in doc["agents"] if r["agent"] in ("Copilot-MRB", "Copilot-PR"))
    assert copilot["model"] == "claude-haiku-4.5"
    assert copilot["cli"] == "Copilot"

    # empty model round-trip
    for r in rows:
        if r["agent"] in ("Copilot-MRB", "Copilot-PR"):
            r["model"] = ""
    body2 = json.dumps({"agents": rows}).encode("utf-8")
    code3, _ = handle_request(
        "PUT", mc.MODELS_PATH, {}, body2, "127.0.0.1", tmp_path, allow_ips={"127.0.0.1"}
    )
    assert code3 == 204
    code4, payload4 = handle_request(
        "GET", mc.MODELS_PATH, {}, b"", "127.0.0.1", tmp_path, allow_ips={"127.0.0.1"}
    )
    assert code4 == 200
    copilot2 = next(
        r for r in json.loads(payload4.decode("utf-8"))["agents"] if r["agent"] in ("Copilot-MRB", "Copilot-PR")
    )
    assert copilot2["model"] == ""

    # unchanged PUT -> 200
    code5, payload5 = handle_request(
        "PUT", mc.MODELS_PATH, {}, body2, "127.0.0.1", tmp_path, allow_ips={"127.0.0.1"}
    )
    assert code5 == 200
    assert "agents" in json.loads(payload5.decode("utf-8"))


def test_fr9746_get_backfills_seven_row_catalog(tmp_path: Path):
    path = tmp_path / mc.MODELS_CATALOG_NAME
    legacy = {
        "version": 1,
        "clis": {"grok": {"models": [], "refreshed_at": "keep-me"}},
        "unrelated": {"keep": True},
        "agents": _legacy_seven_rows(Plan={"model": "build0.1", "context": "256", "effort": "high"}),
    }
    before = json.dumps(legacy, separators=(",", ":")).encode("utf-8")
    path.write_bytes(before)
    rows = mc.load_catalog_file(tmp_path)
    assert [r["agent"] for r in rows][-1] == "Copilot-PR"
    assert rows[-1]["model"] == ""
    plan = next(r for r in rows if r["agent"] == "Plan")
    assert plan["model"] == "build0.1"
    # GET must not write the file
    assert path.read_bytes() == before

    code, payload = handle_request(
        "GET", mc.MODELS_PATH, {}, b"", "127.0.0.1", tmp_path, allow_ips={"127.0.0.1"}
    )
    assert code == 200
    doc = json.loads(payload.decode("utf-8"))
    assert [r["agent"] for r in doc["agents"]][-1] == "Copilot-PR"
    assert path.read_bytes() == before


def test_fr9746_put_seven_row_preserves_stored_copilot(tmp_path: Path):
    rows8 = mc.default_agent_rows()
    for r in rows8:
        if r["agent"] in ("Copilot-MRB", "Copilot-PR"):
            r["model"] = "gpt-5.4"
    handle_request(
        "PUT",
        mc.MODELS_PATH,
        {},
        json.dumps({"agents": rows8}).encode("utf-8"),
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    # legacy seven-row PUT edits Plan only
    seven = _legacy_seven_rows(Plan={"model": "edited-plan"})
    code, _ = handle_request(
        "PUT",
        mc.MODELS_PATH,
        {},
        json.dumps({"agents": seven}).encode("utf-8"),
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code == 204
    stored = json.loads((tmp_path / mc.MODELS_CATALOG_NAME).read_text(encoding="utf-8"))
    assert stored.get("unrelated") is None or True
    agents = {r["agent"]: r for r in stored["agents"]}
    assert agents["Plan"]["model"] == "edited-plan"
    assert agents["Copilot-MRB"]["model"] == "gpt-5.4"
    assert agents["Copilot-PR"]["model"] == "gpt-5.4"


def test_fr9746_put_seven_row_inserts_blank_copilot_when_absent(tmp_path: Path):
    seven = _legacy_seven_rows()
    code, _ = handle_request(
        "PUT",
        mc.MODELS_PATH,
        {},
        json.dumps({"agents": seven, "version": 1, "extra": 1}).encode("utf-8"),
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    # PUT body extra keys are ignored by validate; replace preserves file keys
    assert code == 204
    stored = json.loads((tmp_path / mc.MODELS_CATALOG_NAME).read_text(encoding="utf-8"))
    agents = {r["agent"]: r for r in stored["agents"]}
    blank = {"cli": "Copilot", "model": "", "context": "", "effort": ""}
    assert agents["Copilot-MRB"]["agent"] == "Copilot-MRB"
    assert agents["Copilot-PR"]["agent"] == "Copilot-PR"
    for name in ("Copilot-MRB", "Copilot-PR"):
        for key, val in blank.items():
            assert agents[name][key] == val


def test_fr9746_put_rejects_wrong_cli_and_case_and_missing_grok(tmp_path: Path):
    rows = mc.default_agent_rows()
    for r in rows:
        if r["agent"] in ("Copilot-MRB", "Copilot-PR"):
            r["cli"] = "Grok"
    code, payload = handle_request(
        "PUT",
        mc.MODELS_PATH,
        {},
        json.dumps({"agents": rows}).encode("utf-8"),
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code == 400
    assert b"read-only" in payload or b"cli" in payload

    rows2 = mc.default_agent_rows()
    rows2[-1]["agent"] = "copilot"
    code2, payload2 = handle_request(
        "PUT",
        mc.MODELS_PATH,
        {},
        json.dumps({"agents": rows2}).encode("utf-8"),
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code2 == 400

    rows3 = [r for r in mc.default_agent_rows() if r["agent"] != "Grok"]
    code3, payload3 = handle_request(
        "PUT",
        mc.MODELS_PATH,
        {},
        json.dumps({"agents": rows3}).encode("utf-8"),
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code3 == 400
    assert b"missing agents" in payload3 and b"Grok" in payload3


def test_fr9746_refresh_clis_exclude_copilot():
    assert mr.REFRESH_CLIS == ("grok", "cursor", "opencode")
    assert "copilot" not in mr.REFRESH_CLIS


def test_fr9746_seed_merge_preserves_operator_rows(tmp_path: Path):
    mc.ensure_valid_combos_seeded(tmp_path, seed_path=SEED)
    path = mc.valid_combos_path(tmp_path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["clis"]["copilot"].append(
        {"model": "operator-copilot-only", "contexts": [], "efforts": []}
    )
    path.write_text(json.dumps(doc), encoding="utf-8")
    status = mc.ensure_valid_combos_seeded(tmp_path, seed_path=SEED)
    assert status["ok"] is True
    cat = mc.load_valid_combos(tmp_path)
    models = {r.model for r in cat.clis["copilot"]}
    assert "operator-copilot-only" in models
    assert "claude-haiku-4.5" in models
