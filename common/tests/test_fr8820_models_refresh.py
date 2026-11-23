"""FR #8820: POST /bob/v1/models/refresh acceptance tests (fixture listers)."""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

import models_catalog as mc
import models_refresh as mr
from bobcallback import handle_request

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "models_refresh"


def _seed_catalog(home: Path, *, agents=None, clis=None) -> None:
    doc = {"version": 1, "agents": agents or mc.default_agent_rows(), "clis": clis or {}}
    home.mkdir(parents=True, exist_ok=True)
    (home / mc.MODELS_CATALOG_NAME).write_text(
        json.dumps(doc), encoding="utf-8"
    )


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
    _seed_catalog(
        tmp_path,
        clis={
            "grok": {
                "models": [{"model": "old-g", "contexts": ["1"], "efforts": []}],
                "refreshed_at": "2020-01-01T00:00:00Z",
            },
            "cursor": {
                "models": [{"model": "old-c", "contexts": [], "efforts": []}],
                "refreshed_at": None,
            },
            "opencode": {
                "models": [{"model": "keep-o", "contexts": ["x"], "efforts": ["low"]}],
                "refreshed_at": None,
            },
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
    assert set(payload["clis"]) >= {"grok", "cursor", "opencode"}
    assert payload["refresh"]["grok"]["status"] == "refreshed"
    assert payload["refresh"]["grok"]["added"] == ["new-g"]
    assert payload["refresh"]["grok"]["removed"] == []
    assert payload["refresh"]["cursor"]["added"] == ["new-c"]
    assert payload["refresh"]["cursor"]["removed"] == ["old-c"]
    assert payload["refresh"]["opencode"]["added"] == ["new-o"]
    assert payload["refresh"]["opencode"]["removed"] == []
    # Existing keep-o row preserved verbatim (contexts/efforts).
    oc_models = {m["model"]: m for m in payload["clis"]["opencode"]["models"]}
    assert oc_models["keep-o"]["contexts"] == ["x"]
    assert oc_models["keep-o"]["efforts"] == ["low"]
    assert oc_models["new-o"]["contexts"] == []
    assert oc_models["new-o"]["efforts"] == []


def test_one_cli_failure_keeps_prior_catalog(tmp_path: Path):
    prior = {
        "models": [{"model": "cursor-keep", "contexts": ["64"], "efforts": ["high"]}],
        "refreshed_at": "2021-06-01T00:00:00Z",
    }
    _seed_catalog(tmp_path, clis={"cursor": prior, "grok": {"models": [], "refreshed_at": None}})
    clock, _adv = _fake_clock()

    def boom() -> list[str]:
        raise mr.ListingError(mr.REASON_TIMEOUT)

    ctl = mr.ModelsRefreshController(
        tmp_path,
        listers={
            "grok": lambda: ["g1"],
            "cursor": boom,
            "opencode": lambda: ["opencode/x"],
        },
        clock=clock,
    )
    code, body = ctl.handle(b"")
    assert code == 200
    payload = json.loads(body)
    assert payload["refresh"]["cursor"]["status"] == "failed"
    assert payload["refresh"]["cursor"]["reason"] == "timeout"
    assert payload["refresh"]["cursor"]["refreshed_at"] == "2021-06-01T00:00:00Z"
    assert payload["clis"]["cursor"]["models"][0]["model"] == "cursor-keep"
    assert payload["clis"]["cursor"]["models"][0]["contexts"] == ["64"]
    assert payload["refresh"]["grok"]["status"] == "refreshed"
    assert payload["refresh"]["opencode"]["status"] == "refreshed"

    # Empty listing also fails closed.
    clock2, _ = _fake_clock(2000.0)
    ctl2 = mr.ModelsRefreshController(
        tmp_path,
        listers={
            "grok": lambda: ["g2"],
            "cursor": lambda: [],
            "opencode": lambda: ["opencode/y"],
        },
        clock=clock2,
        rate_window_s=0.0,
    )
    # Force empty via ListingError path inside controller (empty raises).
    def empty() -> list[str]:
        raise mr.ListingError(mr.REASON_EMPTY_LISTING)

    ctl2.listers["cursor"] = empty
    code2, body2 = ctl2.handle(b'{"clis":["cursor"]}')
    assert code2 == 200
    p2 = json.loads(body2)
    assert p2["refresh"]["cursor"]["status"] == "failed"
    assert p2["refresh"]["cursor"]["reason"] == "empty_listing"
    assert p2["clis"]["cursor"]["models"][0]["model"] == "cursor-keep"


def test_stale_selection_unchanged_on_get(tmp_path: Path):
    agents = mc.default_agent_rows()
    for row in agents:
        if row["agent"] == "Plan":
            row["model"] = "grok-x"
            row["cli"] = "Grok"
    _seed_catalog(
        tmp_path,
        agents=agents,
        clis={
            "grok": {
                "models": [{"model": "grok-x", "contexts": [], "efforts": []}],
                "refreshed_at": None,
            }
        },
    )
    clock, _ = _fake_clock()
    ctl = mr.ModelsRefreshController(
        tmp_path,
        listers={
            "grok": lambda: ["grok-y"],
            "cursor": lambda: ["c1"],
            "opencode": lambda: ["opencode/z"],
        },
        clock=clock,
    )
    assert ctl.handle(b"")[0] == 200
    stored = json.loads((tmp_path / mc.MODELS_CATALOG_NAME).read_text(encoding="utf-8"))
    plan = next(r for r in stored["agents"] if r["agent"] == "Plan")
    assert plan["model"] == "grok-x"
    code, body = mc.handle_models_get(tmp_path)
    assert code == 200
    doc = json.loads(body)
    plan_pub = next(r for r in doc["agents"] if r["agent"] == "Plan")
    assert plan_pub["model"] == "grok-x"
    assert plan_pub.get("stale") is True
    # Non-stale rows omit the key.
    for row in doc["agents"]:
        if row["agent"] != "Plan":
            assert "stale" not in row


def test_rate_limit_429_no_change(tmp_path: Path):
    _seed_catalog(
        tmp_path,
        clis={
            "grok": {
                "models": [{"model": "g0", "contexts": [], "efforts": []}],
                "refreshed_at": "2022-01-01T00:00:00Z",
            }
        },
    )
    calls = {"n": 0}

    def lister() -> list[str]:
        calls["n"] += 1
        return ["g1"]

    clock, advance = _fake_clock()
    ctl = mr.ModelsRefreshController(
        tmp_path,
        listers={"grok": lister, "cursor": lister, "opencode": lister},
        clock=clock,
        rate_window_s=60.0,
    )
    assert ctl.handle(b"")[0] == 200
    path = tmp_path / mc.MODELS_CATALOG_NAME
    before = path.read_bytes()
    mtime = path.stat().st_mtime
    n1 = calls["n"]
    code, body = ctl.handle(b"")
    assert code == 429
    err = json.loads(body)
    assert err["error"] == "rate_limited"
    assert err["retry_after_s"] >= 1
    assert path.read_bytes() == before
    assert path.stat().st_mtime == mtime
    assert calls["n"] == n1
    advance(61.0)
    code2, body2 = ctl.handle(b"")
    assert code2 == 200
    p2 = json.loads(body2)
    assert p2["refresh"]["grok"]["added"] == []
    assert p2["refresh"]["grok"]["removed"] == []


def test_bobcallback_route_peer_gate(tmp_path: Path):
    _seed_catalog(tmp_path)
    clock, _ = _fake_clock()
    ctl = mr.ModelsRefreshController(
        tmp_path,
        listers={
            "grok": lambda: ["g"],
            "cursor": lambda: ["c"],
            "opencode": lambda: ["opencode/a"],
        },
        clock=clock,
    )
    code, body = handle_request(
        "POST",
        "/bob/v1/models/refresh",
        {},
        b"",
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
        models_refresh_ctl=ctl,
    )
    assert code == 200
    assert "clis" in json.loads(body)


def test_secret_not_in_response_or_logs(tmp_path: Path, caplog):
    token = "FAKESECRET_m4n5o6p7q8r9s0t1u2v3"
    _seed_catalog(tmp_path)
    clock, _ = _fake_clock()

    def leaky() -> list[str]:
        # Model id itself is fine; ensure raw listing text never lands in logs/response.
        raise mr.ListingError(mr.REASON_SPAWN_ERROR)

    ctl = mr.ModelsRefreshController(
        tmp_path,
        listers={
            "grok": lambda: ["safe-model"],
            "cursor": leaky,
            "opencode": lambda: ["opencode/safe"],
        },
        clock=clock,
    )
    with caplog.at_level(logging.INFO, logger="models_refresh"):
        code, body = ctl.handle(b"")
    assert code == 200
    text = body.decode("utf-8")
    assert token not in text
    assert token not in caplog.text


def test_replace_failure_leaves_file(tmp_path: Path, monkeypatch):
    _seed_catalog(
        tmp_path,
        clis={
            "grok": {
                "models": [{"model": "keep", "contexts": [], "efforts": []}],
                "refreshed_at": None,
            }
        },
    )
    before = (tmp_path / mc.MODELS_CATALOG_NAME).read_text(encoding="utf-8")
    clock, _ = _fake_clock()

    def boom_save(home, doc):
        raise OSError("disk full")

    monkeypatch.setattr(mc, "save_catalog_document", boom_save)
    ctl = mr.ModelsRefreshController(
        tmp_path,
        listers={
            "grok": lambda: ["new"],
            "cursor": lambda: ["c"],
            "opencode": lambda: ["opencode/z"],
        },
        clock=clock,
    )
    code, body = ctl.handle(b"")
    assert code == 503
    assert json.loads(body)["error"] == "catalog_unavailable"
    assert (tmp_path / mc.MODELS_CATALOG_NAME).read_text(encoding="utf-8") == before
