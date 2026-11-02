"""FR #5948: PRIORITY form walk uses read-only SDK by default; fixture is opt-in."""
from __future__ import annotations

import json

import airc_fail_intake as fi
import airc_priority as ap
from repo_layout import ROOT

FIX = ROOT / "airc" / "priority-worker" / "fixtures" / "form_walk.json"


def _allow(tmp_path, inst_id="hrs-dev-live1"):
    allow = tmp_path / "priority-instances.json"
    allow.write_text(
        json.dumps(
            {
                "instances": [
                    {
                        "id": inst_id,
                        "url": "https://prioritydev.example.invalid",
                        "company": "live1",
                        "user": "api-user",
                        "credentialTarget": "PriorityWeb/" + inst_id,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return allow


def test_fr5948_sdk_formstart_found(tmp_path, monkeypatch):
    allow = _allow(tmp_path)
    calls = []

    def sdk(**kw):
        calls.append(kw)
        return {
            "ok": True,
            "op": "formStart",
            "form": "CUSTOMERS",
            "title": "Customers",
            "columns": ["CUSTNAME", "CUSTDES"],
            "rows": [{"CUSTNAME": "A", "CUSTDES": "Acme"}],
            "count": 1,
            "subforms": ["ORDERS"],
        }

    monkeypatch.setattr(fi, "report_verb_failure", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("intake")))
    r = ap.run_priority_walk(
        text="id=aabbccdd PRIORITY formStart instance=hrs-dev-live1 form=CUSTOMERS",
        allowlist_path=allow,
        sdk_walk=sdk,
    )
    assert r.ok and r.exit_code == 0
    assert r.payload["form"] == "CUSTOMERS"
    assert r.payload["columns"] == ["CUSTNAME", "CUSTDES"]
    assert calls and calls[0].get("op") == "formStart"
    assert calls[0].get("form") == "CUSTOMERS"
    assert "password" not in json.dumps(r.payload).lower()


def test_fr5948_sdk_form_not_found_no_intake(tmp_path, monkeypatch):
    allow = _allow(tmp_path)
    reports = []
    monkeypatch.setattr(fi, "report_verb_failure", lambda *a, **kw: reports.append((a, kw)))

    def sdk(**kw):
        return {"ok": False, "error": "form-not-found", "form": "NOPE"}

    r = ap.run_priority_walk(
        text="id=aabbccdd PRIORITY formStart hrs-dev-live1 NOPE",
        allowlist_path=allow,
        sdk_walk=sdk,
    )
    assert not r.ok and r.exit_code == 2
    assert r.payload["error"] == "form-not-found"
    assert reports == []


def test_fr5948_sdk_no_access_no_intake(tmp_path, monkeypatch):
    allow = _allow(tmp_path)
    reports = []
    monkeypatch.setattr(fi, "report_verb_failure", lambda *a, **kw: reports.append((a, kw)))

    def sdk(**kw):
        return {"ok": False, "error": "no-access", "form": "ORDERS"}

    r = ap.run_priority_walk(
        text="id=aabbccdd PRIORITY formStart instance=hrs-dev-live1 form=ORDERS",
        allowlist_path=allow,
        sdk_walk=sdk,
    )
    assert r.payload["error"] == "no-access"
    assert reports == []


def test_fr5948_sdk_getrows_paging(tmp_path, monkeypatch):
    allow = _allow(tmp_path)

    def sdk(**kw):
        assert kw.get("op") == "getRows"
        assert int(kw.get("offset") or 0) == 2
        assert int(kw.get("limit") or 0) == 1
        return {
            "ok": True,
            "op": "getRows",
            "form": "CUSTOMERS",
            "rows": [{"CUSTNAME": "B"}],
            "count": 1,
            "offset": 2,
            "limit": 1,
            "has_more": True,
        }

    r = ap.run_priority_walk(
        text="id=aabbccdd PRIORITY getRows instance=hrs-dev-live1 form=CUSTOMERS offset=2 limit=1",
        allowlist_path=allow,
        sdk_walk=sdk,
    )
    assert r.ok
    assert r.payload["rows"] == [{"CUSTNAME": "B"}]
    assert r.payload.get("has_more") is True


def test_fr5948_fixture_only_when_explicit(tmp_path, monkeypatch):
    allow = _allow(tmp_path, "fixture")
    sdk_calls = {"n": 0}

    def sdk(**kw):
        sdk_calls["n"] += 1
        return {"ok": False, "error": "should-not-run"}

    r = ap.run_priority_walk(
        text="id=aabbccdd PRIORITY formStart instance=fixture form=CUST",
        allowlist_path=allow,
        fixture_path=FIX,
        use_fixture=True,
        sdk_walk=sdk,
    )
    assert r.ok and r.payload["form"] == "CUST"
    assert sdk_calls["n"] == 0


def test_fr5948_default_without_fixture_uses_sdk(tmp_path, monkeypatch):
    allow = _allow(tmp_path)
    seen = {}

    def sdk(**kw):
        seen.update(kw)
        return {"ok": True, "op": "formStart", "form": "ORDERS", "columns": ["ORDNAME"], "rows": [], "count": 0}

    r = ap.run_priority_walk(
        text="id=aabbccdd PRIORITY formStart instance=hrs-dev-live1 form=ORDERS",
        allowlist_path=allow,
        sdk_walk=sdk,
        # no fixture_path / use_fixture
    )
    assert r.ok
    assert seen.get("form") == "ORDERS"
    assert seen.get("instance", {}).get("id") == "hrs-dev-live1"


def test_fr5948_crash_still_intakes(tmp_path, monkeypatch):
    allow = _allow(tmp_path)
    reports = []
    monkeypatch.setattr(fi, "report_verb_failure", lambda *a, **kw: reports.append((a, kw)))

    def sdk(**kw):
        raise RuntimeError("boom")

    r = ap.run_priority_walk(
        text="id=aabbccdd PRIORITY formStart instance=hrs-dev-live1 form=ORDERS",
        allowlist_path=allow,
        sdk_walk=sdk,
    )
    assert not r.ok
    assert r.payload.get("error") in {"sdk-fault", "isolated-fault:RuntimeError"} or "fault" in str(
        r.payload.get("error") or ""
    ).lower() or r.payload.get("error") == "sdk_not_ok"
    assert len(reports) == 1


def test_fr5948_pack_ships_readonly_mjs():
    mjs = ROOT / "airc" / "priority-worker" / "sdk" / "run-formwalk-readonly.mjs"
    assert mjs.is_file()
    text = mjs.read_text(encoding="utf-8")
    assert "PRIORITY_SDK_PASSWORD" in text
    assert "formStart" in text
    assert "readonly" in text.lower()
    # Must not call prepare/activate paths (comment may mention FORMPREP as forbidden).
    assert "activateStart(" not in text
    assert "FORMPREPDRCT" not in text.upper()
    assert not mjs.read_bytes().startswith(b"\xef\xbb\xbf")
