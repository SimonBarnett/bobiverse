"""FR #9266: POST /bob/v1/models/refresh accepts Weights client catalog (no chair CLI spawn)."""
from __future__ import annotations

import json
from pathlib import Path

import models_catalog as mc
import models_refresh as mr


def _seed_catalog(home: Path, *, agents=None, clis=None) -> None:
    doc = {"version": 1, "agents": agents or mc.default_agent_rows(), "clis": clis or {}}
    home.mkdir(parents=True, exist_ok=True)
    (home / mc.MODELS_CATALOG_NAME).write_text(json.dumps(doc), encoding="utf-8")


def _fake_clock(start: float = 1000.0):
    state = {"t": float(start)}

    def now() -> float:
        return state["t"]

    return now


def test_fr9266_client_catalog_merges_without_listers(tmp_path: Path):
    _seed_catalog(
        tmp_path,
        clis={
            "grok": {
                "models": [{"model": "old-g", "contexts": ["256"], "efforts": ["high"]}],
                "refreshed_at": "2020-01-01T00:00:00Z",
            }
        },
    )
    calls = {"n": 0}

    def boom() -> list[str]:
        calls["n"] += 1
        raise AssertionError("chair lister must not run for weights-client")

    clock = _fake_clock()
    ctl = mr.ModelsRefreshController(
        tmp_path,
        listers={"grok": boom, "cursor": boom, "opencode": boom},
        clock=clock,
    )
    body = json.dumps(
        {
            "source": "weights-client",
            "clis": {
                "grok": ["old-g", "new-g"],
                "cursor": [{"model": "cursor-x"}],
                "opencode": ["opencode/deepseek-v4.1-flash-free"],
            },
        }
    ).encode("utf-8")
    code, raw = ctl.handle(body)
    assert code == 200
    assert calls["n"] == 0
    payload = json.loads(raw)
    assert payload["source"] == "weights-client"
    assert payload["refresh"]["grok"]["status"] == "refreshed"
    assert payload["refresh"]["grok"]["added"] == ["new-g"]
    assert payload["refresh"]["cursor"]["status"] == "refreshed"
    assert payload["refresh"]["cursor"]["added"] == ["cursor-x"]
    assert payload["refresh"]["opencode"]["status"] == "refreshed"
    grok_models = {m["model"]: m for m in payload["clis"]["grok"]["models"]}
    assert grok_models["old-g"]["contexts"] == ["256"]
    assert grok_models["old-g"]["efforts"] == ["high"]
    assert grok_models["new-g"]["contexts"] == []


def test_fr9266_client_empty_cli_keeps_prior(tmp_path: Path):
    prior = {
        "models": [{"model": "keep-c", "contexts": [], "efforts": []}],
        "refreshed_at": "2021-01-01T00:00:00Z",
    }
    _seed_catalog(tmp_path, clis={"cursor": prior})
    ctl = mr.ModelsRefreshController(
        tmp_path,
        listers={},
        clock=_fake_clock(),
        rate_window_s=0.0,
    )
    body = json.dumps(
        {"source": "weights-client", "clis": {"cursor": []}}
    ).encode("utf-8")
    code, raw = ctl.handle(body)
    assert code == 200
    payload = json.loads(raw)
    assert payload["refresh"]["cursor"]["status"] == "failed"
    assert payload["refresh"]["cursor"]["reason"] == "empty_listing"
    assert payload["clis"]["cursor"]["models"][0]["model"] == "keep-c"


def test_fr9266_client_unknown_cli_400(tmp_path: Path):
    _seed_catalog(tmp_path)
    ctl = mr.ModelsRefreshController(tmp_path, listers={}, clock=_fake_clock())
    body = json.dumps(
        {"source": "weights-client", "clis": {"claude": ["x"]}}
    ).encode("utf-8")
    code, raw = ctl.handle(body)
    assert code == 400
    assert json.loads(raw)["error"] == "unknown_cli"


def test_fr9266_chair_list_body_still_works(tmp_path: Path):
    _seed_catalog(tmp_path)
    ctl = mr.ModelsRefreshController(
        tmp_path,
        listers={
            "grok": lambda: ["g1"],
            "cursor": lambda: ["c1"],
            "opencode": lambda: ["opencode/a"],
        },
        clock=_fake_clock(),
    )
    code, raw = ctl.handle(b'{"clis":["grok"]}')
    assert code == 200
    payload = json.loads(raw)
    assert "source" not in payload
    assert payload["refresh"]["grok"]["status"] == "refreshed"
    assert "cursor" not in payload["refresh"]
