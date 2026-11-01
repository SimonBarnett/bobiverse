"""MRB #5604 hostile pins for FR #5594 LEGION SYSTEM default identity."""
from __future__ import annotations

import os
from pathlib import Path

import airc_legion as lg


def test_mrb5604_default_path_falls_to_system_when_credman_missing(monkeypatch):
    """FR #5659 amends #5594: CredMan probe then SYSTEM when missing."""
    import airc_identity as ident

    monkeypatch.delenv("AIRC_LEGION_USE_CREDMAN", raising=False)
    monkeypatch.delenv("AIRC_LEGION_PASSWORD", raising=False)
    monkeypatch.setattr(ident, "default_credman_reader", lambda t: {})

    body = lg.installer_legion_work(
        "flamingo",
        whatif=False,
        run_fn=lambda spec: {"ok": True, "status": "ok"},
    )
    assert body["identity"] == "system"
    assert body.get("credman_missing") is True
    assert body["ok"] is True
    assert "password" not in body


def test_mrb5604_empty_credman_falls_through_to_system(monkeypatch):
    monkeypatch.delenv("AIRC_LEGION_PASSWORD", raising=False)

    body = lg.installer_legion_work(
        "walrus",
        whatif=False,
        run_fn=lambda spec: {"ok": True, "status": "ok"},
        credman=lambda: {},
    )
    assert body["ok"] is True
    assert body["identity"] == "system"
    assert body.get("credman_missing") is True
    assert body["invoked_installer"] is True


def test_mrb5604_whatif_plan_reports_system_identity():
    body = lg.installer_legion_work(
        "flamingo",
        whatif=True,
        run_fn=lambda spec: {
            "ok": True,
            "status": "dry-run",
            "msi": "airc-latest.msi",
            "psexec": "C:\\PsExec.exe",
        },
    )
    assert body["whatif"] is True
    assert body["plan"]["identity"].lower().startswith("system")
    assert "(" in body["plan"]["identity"] and body["plan"]["identity"].endswith(")")
    assert body["computer_account"].endswith("$")
    assert body["computer_account"] in body["plan"]["identity"]


def test_mrb5604_ok_true_never_maps_access_denied():
    body = lg.installer_legion_work(
        "flamingo",
        whatif=False,
        run_fn=lambda spec: {
            "ok": True,
            "status": "ok",
            "detail": "touched ADMIN$ via winrm",
        },
    )
    assert body["ok"] is True
    assert body.get("error") != "system-access-denied"


def test_mrb5604_docs_and_skill_contiguous_system_identity():
    root = Path(lg.__file__).resolve().parents[1]
    skill = (root / ".grok" / "skills" / "bobiverse-airc-commands" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "FR #5659" in skill
    assert "SYSTEM" in skill or "system" in skill
    assert "CredMan" in skill or "credman" in skill.lower()
    docs = (root / "docs" / "airc-remote-control.md").read_text(encoding="utf-8")
    assert "computer account" in docs.lower() or "FR #5659" in docs
    assert "system-access-denied" in docs or "Administrators" in docs or "FR #5659" in docs
    assert not Path(lg.__file__).read_bytes().startswith(b"\xef\xbb\xbf")


def test_mrb5604_source_has_identity_order_and_system_denied():
    src = Path(lg.__file__).read_text(encoding="utf-8")
    assert "FR #5594" in src
    assert "FR #5659" in src
    assert "resolve_remote_identity" in src
    assert "system-access-denied" in src
    assert "auth_failed" in src
    # packaged isolated kwargs must not force CredMan on the default accept path
    assert '{"target": target, "whatif": bool(whatif)}' in src
