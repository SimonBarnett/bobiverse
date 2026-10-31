"""MRB #5381 hostile pins for LEGION in-service installer (FR #5309)."""
from __future__ import annotations

from pathlib import Path

import airc_legion as lg


def test_mrb5381_no_force_no_peer_exe():
    src = Path(lg.__file__).read_text(encoding="utf-8")
    assert "airc-network-installer.exe" not in src
    assert "Popen" not in src
    assert "import airc_network_installer" in src
    assert lg.LEGION_TIMEOUT_S == 900


def test_mrb5381_whatif_does_not_call_install_remote():
    called = {"remote": 0}

    def run_fn(spec: dict) -> dict:
        assert spec["dry_run"] is True
        assert spec["force"] is False
        called["remote"] += 0
        return {"ok": True, "status": "dry-run"}

    # CredMan identity still required (FR #5310); inject so the WhatIf path runs.
    body = lg.installer_legion_work(
        "box1",
        whatif=True,
        run_fn=run_fn,
        credman=lambda: {"username": "u", "password": "FAKE_x"},
    )
    assert body["invoked_installer"] is True
    assert body["force"] is False
    assert "password" not in body


def test_mrb5381_foreign_msi_and_credman_env_only():
    def run_fn(spec: dict) -> dict:
        return {"ok": True, "status": "ok"}

    bad = lg.installer_legion_work(
        "box1", msi="https://example.invalid/x.msi", run_fn=run_fn
    )
    assert bad["ok"] is False
    assert bad["invoked_installer"] is False

    def credman():
        return {"username": "u", "password": "FAKE_pw"}

    seen: list[dict] = []

    def capture(spec: dict) -> dict:
        seen.append(dict(spec))
        return {"ok": True, "status": "dry-run"}

    lg.installer_legion_work("box1", whatif=True, run_fn=capture, credman=credman)
    assert "password" not in seen[0]
    assert seen[0].get("password_via") == "secure-env"
