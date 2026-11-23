# -*- coding: utf-8 -*-
"""FR #9250: Bob ear CLI model reports; chair merge/TTL; refresh without local spawn."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import models_catalog as mc
import models_ear_report as ear
import models_refresh as mr
from bobcallback import handle_request


def _seed(home: Path, **extra) -> None:
    doc = {"version": 1, "agents": mc.default_agent_rows(), "clis": {}, **extra}
    home.mkdir(parents=True, exist_ok=True)
    (home / mc.MODELS_CATALOG_NAME).write_text(json.dumps(doc), encoding="utf-8")


def test_merge_several_machines_union(tmp_path: Path):
    _seed(tmp_path)
    ear.apply_machine_cli_report(
        tmp_path,
        "flamingo",
        {"grok": {"status": "ok", "models": ["g-a", "g-b"]}},
        refreshed_at="2026-11-23T06:00:00Z",
        now=1_700_000_000.0,
        ttl_s=7200,
    )
    ear.apply_machine_cli_report(
        tmp_path,
        "redqueen",
        {"grok": {"status": "ok", "models": ["g-b", "g-c"]}},
        refreshed_at="2026-11-23T06:01:00Z",
        now=1_700_000_000.0,
        ttl_s=7200,
    )
    doc = mc.load_catalog_document(tmp_path)
    public = mc.clis_public_from_document(doc)
    ids = [m["model"] for m in public["grok"]["models"]]
    assert ids == ["g-a", "g-b", "g-c"]
    assert set(public["grok"]["machines"]) == {"flamingo", "redqueen"}


def test_ttl_ageout_keeps_other_machine(tmp_path: Path):
    _seed(tmp_path)
    # flamingo reported long ago (aged out); redqueen fresh.
    ear.apply_machine_cli_report(
        tmp_path,
        "flamingo",
        {"grok": {"status": "ok", "models": ["old-only"]}},
        refreshed_at="2020-01-01T00:00:00Z",
        now=1_700_000_000.0,
        ttl_s=7200,
    )
    ear.apply_machine_cli_report(
        tmp_path,
        "redqueen",
        {"grok": {"status": "ok", "models": ["fresh"]}},
        refreshed_at="2026-11-23T06:00:00Z",
        now=1_700_000_000.0,
        ttl_s=7200,
    )
    doc = mc.load_catalog_document(tmp_path)
    public = mc.clis_public_from_document(doc)
    ids = [m["model"] for m in public["grok"]["models"]]
    assert ids == ["fresh"]
    assert public["grok"]["machines"] == ["redqueen"]
    assert "old-only" not in ids


def test_refresh_no_reporter_and_no_cli_spawn(tmp_path: Path, monkeypatch):
    _seed(tmp_path)
    spawned: list[list[str]] = []

    def boom(*a, **k):
        spawned.append(list(a[0]) if a else [])
        raise AssertionError("chair must not spawn CLIs")

    monkeypatch.setattr(subprocess, "run", boom)
    ctl = mr.ModelsRefreshController(tmp_path)  # production path
    assert ctl.use_local_listers is False
    code, body = ctl.handle(b"")
    assert code == 200
    payload = json.loads(body)
    assert payload["mode"] == "ear_reporters"
    assert payload["refresh"]["grok"]["status"] == "no_reporter"
    assert spawned == []


def test_refresh_ok_after_ear_report(tmp_path: Path):
    _seed(tmp_path)
    ear.apply_machine_cli_report(
        tmp_path,
        "flamingo",
        {
            "grok": {"status": "ok", "models": ["g1"]},
            "cursor": {"status": "ok", "models": ["c1"]},
            "opencode": {"status": "ok", "models": ["opencode/x"]},
        },
        refreshed_at="2026-11-23T06:00:00Z",
        now=1_700_000_000.0,
        ttl_s=10_000,
    )
    ctl = mr.ModelsRefreshController(tmp_path)
    code, body = ctl.handle(b"")
    assert code == 200
    payload = json.loads(body)
    assert payload["refresh"]["grok"]["status"] == "ok"
    assert "flamingo" in payload["refresh"]["grok"]["machines"]
    assert any(m["model"] == "g1" for m in payload["clis"]["grok"]["models"])


def test_parse_failure_keeps_last_good(tmp_path: Path):
    _seed(tmp_path)
    ear.apply_machine_cli_report(
        tmp_path,
        "flamingo",
        {"grok": {"status": "ok", "models": ["keep-me"]}},
        refreshed_at="2026-11-23T06:00:00Z",
        now=1_700_000_000.0,
        ttl_s=10_000,
    )
    ear.apply_machine_cli_report(
        tmp_path,
        "flamingo",
        {"grok": {"status": "failed", "reason": "empty_listing", "models": []}},
        refreshed_at="2026-11-23T06:05:00Z",
        now=1_700_000_000.0,
        ttl_s=10_000,
    )
    doc = mc.load_catalog_document(tmp_path)
    public = mc.clis_public_from_document(doc)
    ids = [m["model"] for m in public["grok"]["models"]]
    assert ids == ["keep-me"]


def test_models_report_route(tmp_path: Path):
    _seed(tmp_path)
    body = json.dumps(
        {
            "machine": "flamingo",
            "clis": {"grok": {"status": "ok", "models": ["g-route"]}},
            "refreshed_at": "2026-11-23T06:00:00Z",
        }
    ).encode("utf-8")
    code, resp = handle_request(
        "POST",
        "/bob/v1/models/report",
        {"content-type": "application/json"},
        body,
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code == 200
    payload = json.loads(resp)
    assert payload.get("ok") is True
    assert any(
        m["model"] == "g-route"
        for m in payload["clis"]["grok"]["models"]
    )


def test_valid_combos_fallback_still_loads(tmp_path: Path):
    """Hand-loaded models-valid-combos.json remains a valid override source."""
    _seed(tmp_path)
    mc.ensure_valid_combos_seeded(tmp_path)
    assert mc.valid_combos_path(tmp_path).is_file()
    cat = mc.load_valid_combos(tmp_path)
    public = mc.valid_combos_to_clis_public(cat)
    assert isinstance(public, dict)


def test_collect_local_uses_injected_listers_not_subprocess(tmp_path: Path, monkeypatch):
    spawned = []

    def boom(*a, **k):
        spawned.append(1)
        raise AssertionError("no spawn")

    monkeypatch.setattr(subprocess, "run", boom)
    got = ear.collect_local_cli_listings(
        tmp_path,
        listers={
            "grok": lambda: ["g"],
            "cursor": lambda: ["c"],
            "opencode": lambda: ["opencode/m"],
        },
    )
    assert got["grok"]["models"] == ["g"]
    assert spawned == []


def test_fr9250_deploy_pins():
    """Pack / freeze / ear overlay must ship models_ear_report (chair + tip hotpatch)."""
    from repo_layout import ROOT

    pack = (ROOT / "common/scripts/Pack-BobiverseRelease.ps1").read_text(encoding="utf-8")
    assert "models_ear_report.py" in pack
    build = (ROOT / "jeeves/scripts/Build-Jeeves.ps1").read_text(encoding="utf-8")
    assert "models_ear_report" in build
    agent = (ROOT / "common/scripts/irc_agent.py").read_text(encoding="utf-8")
    assert "models_ear_report" in agent
    assert "MODELS_EAR_REPORT_OVERLAY_MARKER" in agent
    assert "models_ear_report" in (ROOT / "common/scripts/bobcallback.py").read_text(
        encoding="utf-8"
    )
    docs = (ROOT / "jeeves/docs/webhooks.md").read_text(encoding="utf-8")
    assert "models/report" in docs
    assert (ROOT / "jeeves/www/irc-ntsa/docs/webhooks/models-report.html").is_file()
