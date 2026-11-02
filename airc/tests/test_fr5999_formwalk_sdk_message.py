"""FR #5999: formwalk classify emits carry bounded message for intake sdk_message."""
from __future__ import annotations

import json
from pathlib import Path

import airc_fail_intake as fi
import airc_priority as ap
from repo_layout import ROOT

MJS = ROOT / "airc" / "priority-worker" / "sdk" / "run-formwalk-readonly.mjs"


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


def test_fr5999_formwalk_mjs_emits_message_on_formstart_login_getrows():
    src = MJS.read_text(encoding="utf-8")
    assert "function boundedMessage" in src
    assert "boundedMessage(e)" in src
    # formStart / login / getRows classify paths must include message.
    assert src.count("message: boundedMessage(e)") >= 3


def test_fr5999_unclassified_sdk_fault_intakes_with_sdk_message(tmp_path, monkeypatch):
    """Unclassified throw -> sdk-fault + sdk_message in report_verb_failure args."""
    allow = _allow(tmp_path)
    reports = []
    monkeypatch.setattr(fi, "report_verb_failure", lambda *a, **kw: reports.append((a, kw)))

    def sdk(**kw):
        # Shape after FR #5999 mjs formStart catch for an unclassified throw.
        return {
            "ok": False,
            "error": "sdk-fault",
            "op": "formStart",
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
    _a, kw = reports[0]
    args = kw.get("args") or {}
    assert args.get("form") == "CUSTOMERS"
    assert "TypeError" in str(args.get("sdk_message") or "")
    assert "password" not in json.dumps(reports).lower()


def test_fr5999_bounded_message_redacts_secret_shaped_text():
    src = MJS.read_text(encoding="utf-8")
    assert "password=***" in src or "$1=***" in src
