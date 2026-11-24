"""BOB-03 / FR #8710: fail-closed valid combos; POST /models/validate retired (FR #9053)."""
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
                "contexts": ["256", "500"],
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
                "contexts": [],
                "efforts": [],
            }
        ],
        "opencode": [
            {
                "model": "fixture-oc-a",
                "contexts": [],
                "efforts": [],
            }
        ],
        "copilot": [
            {
                "model": "fixture-copilot-a",
                "contexts": [],
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
    assert set(cat.clis) == {"grok", "cursor", "opencode", "copilot"}
    assert "aider" not in cat.clis
    grok_models = [r.model for r in cat.clis["grok"]]
    assert grok_models == ["fixture-grok-a"]
    assert cat.clis["grok"][0].contexts == ["256", "500"]
    assert cat.clis["cursor"][0].contexts == []
    assert cat.clis["opencode"][0].contexts == []
    assert cat.clis["copilot"][0].contexts == []
    assert cat.clis["copilot"][0].efforts == []


def test_validate_combo_accepts_valid(tmp_path: Path):
    _write_combos(tmp_path)
    ok, err, field = mc.validate_combo(
        "Grok", "fixture-grok-a", "256", "HIGH", home=tmp_path
    )
    assert ok and err is None and field is None
    # FR #9258: Cursor/OpenCode — empty context + no effort is valid.
    ok2, err2, field2 = mc.validate_combo(
        "cursor", "fixture-cursor-a", "", None, home=tmp_path
    )
    assert ok2 and err2 is None and field2 is None
    # FR #9746: Copilot — empty context + no effort; nonempty context rejected.
    ok3, err3, field3 = mc.validate_combo(
        "copilot", "fixture-copilot-a", "", None, home=tmp_path
    )
    assert ok3 and err3 is None and field3 is None
    bad_ctx, err_ctx, field_ctx = mc.validate_combo(
        "copilot", "fixture-copilot-a", "256", None, home=tmp_path
    )
    assert bad_ctx is False
    assert err_ctx == mc.ERROR_INVALID_CONTEXT
    assert field_ctx == "context"


def test_validate_combo_rejects_each_field(tmp_path: Path):
    _write_combos(tmp_path)
    assert mc.validate_combo("aider", "x", "y", None, home=tmp_path) == (
        False,
        mc.ERROR_UNKNOWN_CLI,
        "cli",
    )
    assert mc.validate_combo("grok", "nope", "256", "low", home=tmp_path) == (
        False,
        mc.ERROR_UNKNOWN_MODEL,
        "model",
    )
    assert mc.validate_combo(
        "grok", "fixture-grok-a", "bad-ctx", "low", home=tmp_path
    ) == (False, mc.ERROR_INVALID_CONTEXT, "context")
    assert mc.validate_combo(
        "grok", "fixture-grok-a", "256", "turbo", home=tmp_path
    ) == (False, mc.ERROR_INVALID_EFFORT, "effort")
    assert mc.validate_combo(
        "cursor", "fixture-cursor-a", "", "low", home=tmp_path
    ) == (False, mc.ERROR_EFFORT_NOT_SUPPORTED, "effort")
    assert mc.validate_combo(
        "cursor", "fixture-cursor-a", "200k", None, home=tmp_path
    ) == (False, mc.ERROR_INVALID_CONTEXT, "context")
    assert mc.validate_combo(
        "grok", "cursor-models", "256", "low", home=tmp_path
    ) == (False, mc.ERROR_UNKNOWN_MODEL, "model")
    assert mc.validate_combo("grok", "auto", "256", "low", home=tmp_path) == (
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



def test_handle_request_validate_retired_404(tmp_path: Path):
    """FR #9053: POST /models/validate is form-only; route returns 404."""
    _write_combos(tmp_path)
    code, payload = _post_validate(
        tmp_path,
        {"cli": "grok", "model": "auto", "context": "128k", "effort": "low"},
    )
    assert code == 404
    body = payload.decode("utf-8")
    assert "no_models_validate" in body


def test_handle_request_validate_peer_gate_still_404(tmp_path: Path):
    _write_combos(tmp_path)
    code, payload = handle_request(
        "POST",
        mc.MODELS_VALIDATE_PATH,
        {},
        b"{}",
        "8.8.8.8",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    # Retired before peer gate: always JSON 404, never a successful validate.
    assert code == 404
    assert b"no_models_validate" in payload


def test_validate_does_not_touch_models_catalog_json(tmp_path: Path):
    _write_combos(tmp_path)
    path = tmp_path / mc.MODELS_CATALOG_NAME
    before = path.read_bytes() if path.is_file() else b""
    _post_validate(
        tmp_path,
        {"cli": "grok", "model": "auto", "context": "128k", "effort": "low"},
    )
    after = path.read_bytes() if path.is_file() else b""
    assert after == before
