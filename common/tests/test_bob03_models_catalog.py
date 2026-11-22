"""BOB-03 / FR #8710: fail-closed valid combos + POST /bob/v1/models/validate."""
from __future__ import annotations

import json
from pathlib import Path

import models_catalog as mc
from bobcallback import handle_request


FIXTURE = {
    "version": 1,
    "clis": {
        "grok": [
            {
                "model": "fixture-grok-a",
                "contexts": ["128k", "256k"],
                "efforts": ["low", "medium", "high"],
            },
            {
                "model": "fixture-grok-a",
                "contexts": ["should-skip-dup"],
                "efforts": ["low"],
            },
        ],
        "cursor": [
            {
                "model": "fixture-cursor-a",
                "contexts": ["200k"],
                "efforts": [],
            }
        ],
        "opencode": [
            {
                "model": "fixture-oc-a",
                "contexts": ["default"],
                "efforts": [],
            }
        ],
        "aider": [
            {
                "model": "should-ignore",
                "contexts": ["1k"],
                "efforts": [],
            }
        ],
    },
}


def _write_combos(home: Path, doc: dict | None = None) -> Path:
    path = home / mc.MODELS_VALID_COMBOS_NAME
    path.write_text(json.dumps(doc if doc is not None else FIXTURE), encoding="utf-8")
    return path


def test_load_valid_combos_fail_closed_missing(tmp_path: Path):
    cat = mc.load_valid_combos(tmp_path)
    assert cat.available is False


def test_load_valid_combos_fail_closed_malformed(tmp_path: Path):
    (tmp_path / mc.MODELS_VALID_COMBOS_NAME).write_text("{not-json", encoding="utf-8")
    assert mc.load_valid_combos(tmp_path).available is False
    (tmp_path / mc.MODELS_VALID_COMBOS_NAME).write_text("[]", encoding="utf-8")
    assert mc.load_valid_combos(tmp_path).available is False
    (tmp_path / mc.MODELS_VALID_COMBOS_NAME).write_text(
        json.dumps({"version": 1, "clis": {}}), encoding="utf-8"
    )
    assert mc.load_valid_combos(tmp_path).available is False


def test_load_valid_combos_keeps_first_duplicate_and_skips_aider(tmp_path: Path):
    _write_combos(tmp_path)
    cat = mc.load_valid_combos(tmp_path)
    assert cat.available is True
    assert set(cat.clis) == {"grok", "cursor", "opencode"}
    assert "aider" not in cat.clis
    grok_models = [r.model for r in cat.clis["grok"]]
    assert grok_models == ["fixture-grok-a"]
    assert cat.clis["grok"][0].contexts == ["128k", "256k"]


def test_validate_combo_accepts_valid(tmp_path: Path):
    _write_combos(tmp_path)
    ok, err, field = mc.validate_combo(
        "Grok", "fixture-grok-a", "128k", "HIGH", home=tmp_path
    )
    assert ok and err is None and field is None
    ok2, err2, field2 = mc.validate_combo(
        "cursor", "fixture-cursor-a", "200k", None, home=tmp_path
    )
    assert ok2 and err2 is None and field2 is None


def test_validate_combo_rejects_each_field(tmp_path: Path):
    _write_combos(tmp_path)
    assert mc.validate_combo("aider", "x", "y", None, home=tmp_path) == (
        False,
        mc.ERROR_UNKNOWN_CLI,
        "cli",
    )
    assert mc.validate_combo("grok", "nope", "128k", "low", home=tmp_path) == (
        False,
        mc.ERROR_UNKNOWN_MODEL,
        "model",
    )
    assert mc.validate_combo(
        "grok", "fixture-grok-a", "bad-ctx", "low", home=tmp_path
    ) == (False, mc.ERROR_INVALID_CONTEXT, "context")
    assert mc.validate_combo(
        "grok", "fixture-grok-a", "128k", "turbo", home=tmp_path
    ) == (False, mc.ERROR_INVALID_EFFORT, "effort")
    assert mc.validate_combo(
        "cursor", "fixture-cursor-a", "200k", "low", home=tmp_path
    ) == (False, mc.ERROR_EFFORT_NOT_SUPPORTED, "effort")
    assert mc.validate_combo(
        "grok", "cursor-models", "128k", "low", home=tmp_path
    ) == (False, mc.ERROR_UNKNOWN_MODEL, "model")
    assert mc.validate_combo("grok", "auto", "128k", "low", home=tmp_path) == (
        False,
        mc.ERROR_UNKNOWN_MODEL,
        "model",
    )


def test_validate_combo_catalog_unavailable(tmp_path: Path):
    assert mc.validate_combo("grok", "x", "y", "low", home=tmp_path) == (
        False,
        mc.ERROR_CATALOG_UNAVAILABLE,
        None,
    )


def _post_validate(home: Path, body: dict | bytes, peer: str = "127.0.0.1"):
    raw = body if isinstance(body, (bytes, bytearray)) else json.dumps(body).encode("utf-8")
    return handle_request(
        "POST",
        mc.MODELS_VALIDATE_PATH,
        {"Content-Type": "application/json"},
        raw,
        peer,
        home,
        allow_ips={"127.0.0.1"},
    )


def test_handle_request_validate_ok_and_reject(tmp_path: Path):
    _write_combos(tmp_path)
    before = sorted(p.name for p in tmp_path.iterdir())
    code, payload = _post_validate(
        tmp_path,
        {
            "cli": "grok",
            "model": "fixture-grok-a",
            "context": "128k",
            "effort": "medium",
        },
    )
    assert code == 200
    assert json.loads(payload.decode("utf-8")) == {"ok": True}

    code2, payload2 = _post_validate(
        tmp_path,
        {"cli": "grok", "model": "nope", "context": "128k", "effort": "low"},
    )
    assert code2 == 400
    doc = json.loads(payload2.decode("utf-8"))
    assert doc["error"] == mc.ERROR_UNKNOWN_MODEL
    assert doc["field"] == "model"
    after = sorted(p.name for p in tmp_path.iterdir())
    assert after == before


def test_handle_request_validate_malformed_and_unavailable(tmp_path: Path):
    code, payload = _post_validate(tmp_path, b"not-json")
    assert code == 400
    assert json.loads(payload.decode("utf-8"))["error"] == mc.ERROR_MALFORMED

    code2, payload2 = _post_validate(
        tmp_path, {"cli": "grok", "model": "x", "context": "y", "effort": "low"}
    )
    assert code2 == 503
    assert json.loads(payload2.decode("utf-8"))["error"] == mc.ERROR_CATALOG_UNAVAILABLE


def test_handle_request_validate_peer_gate_and_get(tmp_path: Path):
    _write_combos(tmp_path)
    code, _payload = handle_request(
        "POST",
        mc.MODELS_VALIDATE_PATH,
        {"Content-Type": "application/json"},
        json.dumps(
            {
                "cli": "grok",
                "model": "fixture-grok-a",
                "context": "128k",
                "effort": "low",
            }
        ).encode("utf-8"),
        "203.0.113.9",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code == 403

    code2, payload2 = handle_request(
        "GET",
        mc.MODELS_VALIDATE_PATH,
        {},
        b"",
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code2 == 405
    assert payload2 == b""


def test_validate_does_not_touch_models_catalog_json(tmp_path: Path):
    _write_combos(tmp_path)
    agents = tmp_path / mc.MODELS_CATALOG_NAME
    agents.write_text(json.dumps({"agents": []}), encoding="utf-8")
    stamp = agents.read_bytes()
    _post_validate(
        tmp_path,
        {"cli": "grok", "model": "nope", "context": "128k", "effort": "low"},
    )
    assert agents.read_bytes() == stamp
