"""FR #5991: formStart sdk-fault noise — classify expected SDK outcomes; real crashes still intake."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import airc_console as ac
import airc_fail_intake as fi
import airc_priority as ap
from repo_layout import ROOT

FIX = ROOT / "airc" / "priority-worker" / "fixtures" / "form_walk.json"


def _allow(tmp_path: Path) -> Path:
    p = tmp_path / "priority-instances.json"
    p.write_text(
        json.dumps(
            {
                "instances": [
                    {
                        "id": "hrs-dev-live1",
                        "url": "https://prioritydev.example.invalid",
                        "company": "live1",
                        "user": "api-user",
                        "credentialTarget": "PriorityWeb/hrs-dev-live1",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return p


def test_fr5991_classify_error_maps_common_form_open_messages():
    mjs = (
        ROOT / "airc" / "priority-worker" / "sdk" / "run-formwalk-readonly.mjs"
    ).read_text(encoding="utf-8")
    # Source pin: expanded classify patterns for Priority formStart noise.
    assert "does not exist" in mjs
    assert "cannot open" in mjs or "failed to open" in mjs
    assert "password-refused" in mjs
    assert "need --name and PRIORITY_SDK_PASSWORD" in mjs


def test_fr5991_unprepared_or_missing_form_message_no_intake(tmp_path, monkeypatch):
    allow = _allow(tmp_path)
    reports = []
    monkeypatch.setattr(fi, "report_verb_failure", lambda *a, **kw: reports.append((a, kw)))

    def sdk(**kw):
        # Simulates console normalization after mjs classifyError.
        return {"ok": False, "error": "form-not-found", "form": "CUSTOMERS", "message": "Form is unprepared"}

    r = ap.run_priority_walk(
        text="id=aabbccdd PRIORITY formStart instance=hrs-dev-live1 form=CUSTOMERS",
        allowlist_path=allow,
        sdk_walk=sdk,
    )
    assert not r.ok
    assert r.payload["error"] == "form-not-found"
    assert reports == []


def test_fr5991_sdk_timeout_no_intake(tmp_path, monkeypatch):
    allow = _allow(tmp_path)
    reports = []
    monkeypatch.setattr(fi, "report_verb_failure", lambda *a, **kw: reports.append((a, kw)))

    def sdk(**kw):
        return {"ok": False, "error": "sdk-timeout", "form": "CUSTOMERS", "op": "formStart"}

    r = ap.run_priority_walk(
        text="id=aabbccdd PRIORITY formStart instance=hrs-dev-live1 form=CUSTOMERS",
        allowlist_path=allow,
        sdk_walk=sdk,
    )
    assert not r.ok
    assert r.payload["error"] == "sdk-timeout"
    assert reports == []


def test_fr5991_formwalk_timeout_maps_to_sdk_timeout(monkeypatch):
    calls = {}

    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="node", timeout=120)

    monkeypatch.setattr(
        ac,
        "_priority",
        type(
            "P",
            (),
            {
                "resolve_priority_worker_dir": staticmethod(lambda *_a, **_k: ROOT / "airc" / "priority-worker"),
                "fetch_credman_password": staticmethod(lambda *_a, **_k: "FAKE_secret"),
            },
        )(),
    )
    # Ensure mjs path resolves
    out = ac._priority_sdk_formwalk(
        op="formStart",
        form="CUSTOMERS",
        instance={
            "id": "hrs-dev-live1",
            "url": "https://prioritydev.example.invalid",
            "company": "live1",
            "user": "api-user",
            "credentialTarget": "PriorityWeb/hrs-dev-live1",
        },
        node_runner=boom,
    )
    assert out.get("ok") is False
    assert out.get("error") == "sdk-timeout"
    assert "password" not in json.dumps(out).lower()


def test_fr5991_genuine_sdk_fault_still_intakes_with_message(tmp_path, monkeypatch):
    allow = _allow(tmp_path)
    reports = []
    monkeypatch.setattr(fi, "report_verb_failure", lambda *a, **kw: reports.append((a, kw)))

    def sdk(**kw):
        return {
            "ok": False,
            "error": "sdk-fault",
            "form": "CUSTOMERS",
            "message": "TypeError: cannot read property of undefined",
        }

    r = ap.run_priority_walk(
        text="id=aabbccdd PRIORITY formStart instance=hrs-dev-live1 form=CUSTOMERS",
        allowlist_path=allow,
        sdk_walk=sdk,
    )
    assert not r.ok
    assert r.payload.get("error") == "sdk-fault"
    assert len(reports) == 1
    # Intake args should carry the SDK message for triage (no secrets).
    _a, kw = reports[0]
    args = kw.get("args") or {}
    assert args.get("form") == "CUSTOMERS"
    assert "TypeError" in str(args.get("sdk_message") or args.get("message") or "")
    assert "password" not in json.dumps(reports).lower()
