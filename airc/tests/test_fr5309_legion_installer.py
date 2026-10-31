"""FR #5309: LEGION invokes in-service airc_network_installer for one target."""
from __future__ import annotations

from pathlib import Path

import airc_console as ac
import airc_legion as lg
from airc_auth_helpers import ops_auth


def test_fr5309_whatif_dry_run_no_remote_install():
    seen: list[dict] = []

    def run_fn(spec: dict) -> dict:
        seen.append(spec)
        return {"ok": True, "status": "dry-run"}

    body = lg.installer_legion_work(
        "walrus",
        whatif=True,
        run_fn=run_fn,
        credman=lambda: {"username": "u", "password": "FAKE_x"},
    )
    assert body["ok"] is True
    assert body["invoked_installer"] is True
    assert body["whatif"] is True
    assert body["dry_run"] is True
    assert body["profile"] == "client"
    assert body["force"] is False
    assert body["timeout_s"] == 900
    assert body["hosts"] == ["walrus"]
    assert seen and seen[0]["dry_run"] is True
    assert seen[0]["force"] is False
    assert seen[0]["profile"] == "client"
    assert seen[0]["hosts"] == ["walrus"]
    assert "password" not in body
    assert "password" not in seen[0]


def test_fr5309_live_spec_latest_release_not_foreign_url():
    def run_fn(spec: dict) -> dict:
        return {"ok": True, "status": "success", "msi": spec.get("msi")}

    body = lg.installer_legion_work(
        "10.0.0.8",
        whatif=False,
        run_fn=run_fn,
        msi="https://github.com/SimonBarnett/bobiverse/releases/download/v1/airc.msi",
        credman=lambda: {"username": "u", "password": "FAKE_x"},
    )
    assert body["ok"] is True
    assert body["invoked_installer"] is True
    assert body["dry_run"] is False

    bad = lg.installer_legion_work(
        "box1",
        msi="https://evil.example/airc.msi",
        run_fn=run_fn,
    )
    assert bad["ok"] is False
    assert "foreign" in (bad.get("error") or "").lower()
    assert bad.get("invoked_installer") is False


def test_fr5309_credman_not_on_irc_or_argv():
    captured: list[dict] = []

    def run_fn(spec: dict) -> dict:
        captured.append(spec)
        return {"ok": True, "status": "dry-run"}

    def credman():
        return {"username": "wonderland\\legion", "password": "FAKE_legion_secret"}

    body = lg.installer_legion_work(
        "walrus", whatif=True, run_fn=run_fn, credman=credman
    )
    blob = str(body).lower()
    assert "fake_legion_secret" not in blob
    assert "password" not in body
    assert captured[0].get("username") == "wonderland\\legion"
    assert "password" not in captured[0]
    assert captured[0].get("password_via") == "secure-env"


def test_fr5309_does_not_shell_peer_exe():
    src = Path(lg.__file__).read_text(encoding="utf-8")
    assert "Popen" not in src
    assert "airc-network-installer.exe" not in src
    assert "from airc_network_installer" in src or "import airc_network_installer" in src


def test_fr5309_console_whatif_no_secret():
    auth = ops_auth("op", channel="#tm")

    def runner(**kw):
        return lg.run_legion_verb(
            worker=lambda target, **k: lg.installer_legion_work(
                target,
                run_fn=lambda spec: {"ok": True, "status": "dry-run"},
                credman=lambda: {"username": "u", "password": "FAKE_x"},
                **k,
            ),
            **kw,
        )

    core = ac.AircConsoleCore(
        machine="tm", auth=auth, nick="tm_console", legion_runner=runner
    )
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=aabbccdd LEGION walrus -WhatIf")
    assert hr and hr.action == "legion"
    assert "LEGION accepted" in (hr.reply or "")
    assert "password=" not in (hr.reply or "").lower()
    assert "--force" not in (hr.reply or "").lower()
