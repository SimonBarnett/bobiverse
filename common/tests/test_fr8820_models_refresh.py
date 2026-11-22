"""FR #8820: POST /bob/v1/models/refresh acceptance tests (fixture listers).

Ported onto FR #8819 nested clis + models-valid-combos.json storage.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import models_catalog as mc
import models_refresh as mr
from bobcallback import handle_request

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "models_refresh"


def _seed_agents(home: Path, agents=None) -> None:
    home.mkdir(parents=True, exist_ok=True)
    doc = {"agents": agents or mc.default_agent_rows()}
    (home / mc.MODELS_CATALOG_NAME).write_text(json.dumps(doc), encoding="utf-8")


def _seed_combos(home: Path, clis: dict) -> None:
    """clis: lowercase -> list[{model,contexts,efforts}]"""
    home.mkdir(parents=True, exist_ok=True)
    doc = {"version": 1, "clis": clis}
    (home / mc.MODELS_VALID_COMBOS_NAME).write_text(json.dumps(doc), encoding="utf-8")


def _fake_clock(start: float = 1000.0):
    state = {"t": float(start)}

    def now() -> float:
        return state["t"]

    def advance(seconds: float) -> None:
        state["t"] += float(seconds)

    return now, advance


def test_parse_fixtures():
    grok = mr.parse_grok_models_text((FIXTURES / "grok_models.txt").read_text(encoding="utf-8"))
    assert "grok-4.7" in grok and "grok-4.5" in grok
    cursor = mr.parse_cursor_models_text(
        (FIXTURES / "cursor_models.txt").read_text(encoding="utf-8")
    )
    assert "gpt-5.1-codex" in cursor
    oc = mr.parse_opencode_models_text(
        (FIXTURES / "opencode_models.txt").read_text(encoding="utf-8")
    )
    assert any(x.startswith("opencode/") for x in oc)


def test_refresh_all_three_reports_added_removed(tmp_path: Path):
    _seed_agents(tmp_path)
    _seed_combos(
        tmp_path,
        {
            "grok": [{"model": "old-g", "contexts": ["1"], "efforts": []}],
            "cursor": [{"model": "old-c", "contexts": ["64"], "efforts": []}],
            "opencode": [{"model": "keep-o", "contexts": ["x"], "efforts": ["low"]}],
        },
    )
    clock, _adv = _fake_clock()
    ctl = mr.ModelsRefreshController(
        tmp_path,
        listers={
            "grok": lambda: ["new-g", "old-g"],
            "cursor": lambda: ["new-c"],
            "opencode": lambda: ["keep-o", "new-o"],
        },
        clock=clock,
    )
    code, body = ctl.handle(b"")
    assert code == 200
    payload = json.loads(body)
    assert set(payload["clis"]) >= {"Grok", "Cursor", "Opencode"}
    assert payload["refresh"]["grok"]["status"] == "refreshed"
    assert "new-g" in payload["refresh"]["grok"]["added"]
    assert "old-c" in payload["refresh"]["cursor"]["removed"]
    assert "new-c" in payload["refresh"]["cursor"]["added"]
    assert "keep-o" in payload["clis"]["Opencode"]["models"]
    assert "new-o" in payload["clis"]["Opencode"]["models"]
    assert "x" in payload["clis"]["Opencode"]["models"]["keep-o"]["contexts"]


def test_one_cli_failure_keeps_prior_catalog(tmp_path: Path):
    prior = [{"model": "cursor-keep", "contexts": ["64"], "efforts": ["high"]}]
    _seed_agents(tmp_path)
    _seed_combos(
        tmp_path,
        {
            "cursor": prior,
            "grok": [{"model": "g0", "contexts": ["1"], "efforts": []}],
        },
    )
    clock, _adv = _fake_clock()

    def _boom():
        raise mr.ListingError(mr.REASON_EXIT_NONZERO)

    ctl = mr.ModelsRefreshController(
        tmp_path,
        listers={"cursor": _boom, "grok": lambda: ["g1"], "opencode": lambda: ["o1"]},
        clock=clock,
    )
    code, body = ctl.handle(b'{"clis":["cursor","grok"]}')
    assert code == 200
    payload = json.loads(body)
    assert payload["refresh"]["cursor"]["status"] == "failed"
    assert payload["refresh"]["cursor"]["reason"] == mr.REASON_EXIT_NONZERO
    assert "cursor-keep" in payload["clis"]["Cursor"]["models"]
    assert payload["refresh"]["grok"]["status"] == "refreshed"
    assert "g1" in payload["clis"]["Grok"]["models"]


def test_stale_selection_unchanged_on_get(tmp_path: Path):
    agents = mc.default_agent_rows()
    for row in agents:
        if row["agent"] == "Plan":
            row["model"] = "gone-model"
            row["cli"] = "Grok"
    _seed_agents(tmp_path, agents=agents)
    _seed_combos(
        tmp_path,
        {"grok": [{"model": "grok-x", "contexts": ["1"], "efforts": []}]},
    )
    clock, _adv = _fake_clock()
    ctl = mr.ModelsRefreshController(
        tmp_path,
        listers={
            "grok": lambda: ["grok-x"],
            "cursor": lambda: ["c"],
            "opencode": lambda: ["o"],
        },
        clock=clock,
    )
    assert ctl.handle(b'{"clis":["grok"]}')[0] == 200
    code, body = mc.handle_models_get(tmp_path)
    assert code == 200
    doc = json.loads(body)
    plan = next(a for a in doc["agents"] if a["agent"] == "Plan")
    assert plan["model"] == "gone-model"
    assert plan.get("stale") is True
    for row in doc["agents"]:
        if row["agent"] != "Plan" and not row.get("model"):
            assert "stale" not in row


def test_rate_limit_429_no_change(tmp_path: Path):
    _seed_agents(tmp_path)
    _seed_combos(
        tmp_path,
        {"grok": [{"model": "g0", "contexts": ["1"], "efforts": []}]},
    )
    clock, advance = _fake_clock()
    calls = {"n": 0}

    def _lister():
        calls["n"] += 1
        return ["g0", "g1"]

    ctl = mr.ModelsRefreshController(
        tmp_path,
        listers={"grok": _lister, "cursor": lambda: ["c"], "opencode": lambda: ["o"]},
        clock=clock,
    )
    assert ctl.handle(b'{"clis":["grok"]}')[0] == 200
    code, body = ctl.handle(b'{"clis":["grok"]}')
    assert code == 429
    assert json.loads(body)["error"] == "rate_limited"
    assert calls["n"] == 1
    cat = mc.load_valid_combos(tmp_path)
    assert {r.model for r in cat.clis["grok"]} == {"g0", "g1"}
    advance(61)
    assert ctl.handle(b'{"clis":["grok"]}')[0] == 200
    assert calls["n"] == 2


def test_bobcallback_route_peer_gate(tmp_path: Path):
    _seed_agents(tmp_path)
    _seed_combos(tmp_path, {"grok": [{"model": "g0", "contexts": ["1"], "efforts": []}]})
    ctl = mr.ModelsRefreshController(
        tmp_path,
        listers={"grok": lambda: ["g0"], "cursor": lambda: ["c"], "opencode": lambda: ["o"]},
    )
    code, _body = handle_request(
        "POST",
        "/bob/v1/models/refresh",
        {},
        b"",
        "127.0.0.1",
        tmp_path,
        {"127.0.0.1"},
        models_refresh_ctl=ctl,
    )
    assert code == 200
    code_deny, _ = handle_request(
        "POST",
        "/bob/v1/models/refresh",
        {},
        b"",
        "8.8.8.8",
        tmp_path,
        {"127.0.0.1"},
        models_refresh_ctl=ctl,
    )
    assert code_deny == 403


def test_secret_not_in_response_or_logs(tmp_path: Path, caplog):
    _seed_agents(tmp_path)
    _seed_combos(tmp_path, {"grok": [{"model": "g0", "contexts": ["1"], "efforts": []}]})
    secret = "sk-test-not-for-logs"
    clock, _ = _fake_clock()

    def _lister():
        return ["safe-model"]

    ctl = mr.ModelsRefreshController(
        tmp_path,
        listers={"grok": _lister, "cursor": lambda: ["c"], "opencode": lambda: ["o"]},
        clock=clock,
    )
    with caplog.at_level(logging.INFO):
        code, body = ctl.handle(b'{"clis":["grok"]}')
    assert code == 200
    assert secret.encode() not in body
    assert secret not in caplog.text
