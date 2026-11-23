"""BOB-04 / FR #8709: seed models-valid-combos.json (S1)."""
from __future__ import annotations

import json
from pathlib import Path

import models_catalog as mc
from bobcallback import handle_request
from repo_layout import REPO

SEED = REPO / "common" / "defaults" / "models-valid-combos.seed.json"
EXAMPLE = REPO / "common" / "defaults" / "models-valid-combos.example.json"


def test_bob04_seed_file_covers_all_clis_with_provenance():
    assert SEED.is_file(), "shipped seed missing"
    raw = json.loads(SEED.read_text(encoding="utf-8"))
    doc = mc.load_seed_document(SEED)
    assert set(doc["clis"]) == set(mc.VALID_CLI_KEYS)
    prov = raw.get("provenance") or {}
    assert isinstance(prov, dict)
    for cli in mc.VALID_CLI_KEYS:
        assert cli in (prov.get("clis") or {}), f"provenance missing {cli}"
        assert doc["clis"][cli], f"empty seed rows for {cli}"
        src = str((prov.get("clis") or {}).get(cli, {}).get("source") or "")
        assert src.strip(), f"provenance source empty for {cli}"


def test_bob04_every_seed_row_passes_validate_combo_row():
    doc = mc.load_seed_document(SEED)
    for cli, rows in doc["clis"].items():
        for item in rows:
            row, why = mc.validate_combo_row(item, cli=cli)
            assert row is not None, (cli, item, why)


def test_bob04_seed_creates_nonempty_store(tmp_path: Path):
    status = mc.ensure_valid_combos_seeded(tmp_path, seed_path=SEED)
    assert status["ok"] is True
    assert status["action"] == "created"
    assert status["added"] > 0
    cat = mc.load_valid_combos(tmp_path)
    assert cat.available is True
    assert set(cat.clis) == set(mc.VALID_CLI_KEYS)


def test_bob04_seed_idempotent(tmp_path: Path):
    first = mc.ensure_valid_combos_seeded(tmp_path, seed_path=SEED)
    second = mc.ensure_valid_combos_seeded(tmp_path, seed_path=SEED)
    assert first["ok"] and second["ok"]
    assert second["action"] == "unchanged"
    assert second["added"] == 0


def test_bob04_preserves_operator_rows(tmp_path: Path):
    mc.ensure_valid_combos_seeded(tmp_path, seed_path=SEED)
    path = mc.valid_combos_path(tmp_path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["clis"]["grok"].append(
        {"model": "operator-only-model", "contexts": ["256"], "efforts": ["low"]}
    )
    path.write_text(json.dumps(doc), encoding="utf-8")
    status = mc.ensure_valid_combos_seeded(tmp_path, seed_path=SEED)
    assert status["ok"] is True
    cat = mc.load_valid_combos(tmp_path)
    models = {r.model for r in cat.clis["grok"]}
    assert "operator-only-model" in models


def test_bob04_malformed_store_left_unchanged(tmp_path: Path):
    path = mc.valid_combos_path(tmp_path)
    path.write_text("{not-json", encoding="utf-8")
    before = path.read_bytes()
    status = mc.ensure_valid_combos_seeded(tmp_path, seed_path=SEED)
    assert status["ok"] is False
    assert "store_malformed" in status["error"]
    assert path.read_bytes() == before


def test_bob04_validator_accepts_seeded_rejects_unseeded(tmp_path: Path):
    mc.ensure_valid_combos_seeded(tmp_path, seed_path=SEED)
    cat = mc.load_valid_combos(tmp_path)
    grok = cat.clis["grok"][0]
    effort = grok.efforts[0] if grok.efforts else None
    ok, err, _field = mc.validate_combo(
        "grok", grok.model, grok.contexts[0], effort, catalog=cat
    )
    assert ok is True and err is None
    ok2, err2, field2 = mc.validate_combo(
        "grok", "invented-model-xyz", grok.contexts[0], effort, catalog=cat
    )
    assert ok2 is False
    assert err2 == mc.ERROR_UNKNOWN_MODEL
    assert field2 == "model"


def test_bob04_get_models_after_seed_nonempty(tmp_path: Path):
    mc.ensure_valid_combos_seeded(tmp_path, seed_path=SEED)
    code, body = handle_request(
        "GET",
        "/bob/v1/models",
        {},
        b"",
        "127.0.0.1",
        home=tmp_path,
    )
    assert code == 200
    doc = json.loads(body.decode("utf-8"))
    assert isinstance(doc.get("agents"), list) and doc["agents"]


def test_bob04_pack_and_build_pin_seed():
    pack = (REPO / "common" / "scripts" / "Pack-BobiverseRelease.ps1").read_text(encoding="utf-8")
    build = (REPO / "jeeves" / "scripts" / "Build-Jeeves.ps1").read_text(encoding="utf-8")
    cb = (REPO / "common" / "scripts" / "bobcallback.py").read_text(encoding="utf-8")
    assert "models-valid-combos.seed.json" in pack
    assert "models-valid-combos.seed.json" in build
    assert "ensure_valid_combos_seeded" in cb
    assert EXAMPLE.is_file()


def test_bob04_seed_and_example_are_distinct():
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    example = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    seed_models = {r["model"] for r in seed["clis"]["grok"]}
    example_models = {r["model"] for r in example["clis"]["grok"]}
    assert "fixture-grok-a" in example_models
    assert "fixture-grok-a" not in seed_models
