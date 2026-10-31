"""MRB #5604 hostile pins for FR #5594 LEGION SYSTEM default identity."""
from __future__ import annotations

import os
from pathlib import Path

import airc_legion as lg


def test_mrb5604_default_path_never_touches_credman(monkeypatch):
    hits = {"n": 0}

    def boom():
        hits["n"] += 1
        raise AssertionError("CredMan must stay off the default SYSTEM path")

    monkeypatch.delenv("AIRC_LEGION_USE_CREDMAN", raising=False)
    monkeypatch.delenv("AIRC_LEGION_PASSWORD", raising=False)
    monkeypatch.setattr(lg, "default_legion_credman", boom)
    monkeypatch.setattr(lg, "read_legion_credman", boom)

    body = lg.installer_legion_work(
        "flamingo",
        whatif=False,
        run_fn=lambda spec: {"ok": True, "status": "ok"},
    )
    assert hits["n"] == 0
    assert body["identity"] == "SYSTEM"
    assert body["ok"] is True
    assert "password" not in body


def test_mrb5604_usecredman_env_still_engages_fallback(monkeypatch):
    monkeypatch.setenv("AIRC_LEGION_USE_CREDMAN", "1")
    monkeypatch.delenv("AIRC_LEGION_PASSWORD", raising=False)

    body = lg.installer_legion_work(
        "walrus",
        whatif=False,
        run_fn=lambda spec: (_ for _ in ()).throw(AssertionError("no install")),
        credman=lambda: {},
    )
    assert body["ok"] is False
    assert body["error"] == "credman-missing"
    assert body["invoked_installer"] is False


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
    assert body["plan"]["identity"].startswith("SYSTEM")
    assert body["plan"]["identity"].endswith("$") or "\\" in body["plan"]["identity"]
    assert body["computer_account"].endswith("$")


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
    assert "Default identity SYSTEM" in skill
    assert "AIRC_LEGION_USE_CREDMAN=1" in skill
    docs = (root / "docs" / "airc-remote-control.md").read_text(encoding="utf-8")
    assert "computer account" in docs.lower()
    assert "system-access-denied" in docs or "Administrators" in docs
    assert not Path(lg.__file__).read_bytes().startswith(b"\xef\xbb\xbf")


def test_mrb5604_source_default_gate_is_env_or_explicit_credman():
    src = Path(lg.__file__).read_text(encoding="utf-8")
    assert "FR #5594" in src
    assert "_credman_fallback_requested" in src
    assert 'use_credman = credman is not None or _credman_fallback_requested()' in src
    assert "system-access-denied" in src
    # packaged isolated kwargs must not force CredMan on the default accept path
    assert '{"target": target, "whatif": bool(whatif)}' in src
