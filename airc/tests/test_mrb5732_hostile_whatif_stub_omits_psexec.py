"""MRB #5732: WhatIf stub runners that omit psexec must not invent psexec-missing."""
from __future__ import annotations

import airc_legion as lg


def _stub_readable_profile(monkeypatch) -> None:
    """FR #5781: unread share refuses without -Profile; WhatIf stubs need a readable mock."""
    monkeypatch.setattr(
        lg,
        "read_remote_airc_profile_result",
        lambda host, **_k: {
            "profile": "fleet",
            "ok": True,
            "found": True,
            "detail": "",
        },
    )


def test_mrb5732_whatif_stub_without_psexec_stays_ok(monkeypatch):
    _stub_readable_profile(monkeypatch)

    def run_fn(spec: dict) -> dict:
        assert spec.get("dry_run") is True
        return {"ok": True, "status": "dry-run", "msi": "latest"}

    body = lg.installer_legion_work(
        "walrus",
        whatif=True,
        run_fn=run_fn,
        credman=lambda: {"username": "u", "password": "FAKE_x"},
    )
    assert body["ok"] is True
    assert body["invoked_installer"] is True
    assert (body.get("plan") or {}).get("psexec") == "psexec-missing"
    assert "will_fail" not in (body.get("plan") or {})


def test_mrb5732_whatif_explicit_missing_still_fails(monkeypatch):
    _stub_readable_profile(monkeypatch)

    def run_fn(spec: dict) -> dict:
        return {
            "ok": False,
            "status": "failed",
            "error": "psexec-missing",
            "psexec": "psexec-missing",
        }

    body = lg.installer_legion_work(
        "walrus",
        whatif=True,
        run_fn=run_fn,
        credman=lambda: {"username": "u", "password": "FAKE_x"},
    )
    assert body["ok"] is False
    assert (body.get("plan") or {}).get("will_fail") == "psexec-missing"
