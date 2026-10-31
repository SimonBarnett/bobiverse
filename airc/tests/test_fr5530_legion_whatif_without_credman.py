"""FR #5530: LEGION -WhatIf still plans when CredMan is missing."""
from __future__ import annotations

from pathlib import Path

import airc_legion as lg


def test_fr5530_whatif_invokes_runner_without_secret():
    seen: list[dict] = []

    def run_fn(spec: dict) -> dict:
        seen.append(spec)
        return {"ok": True, "status": "dry-run", "msi": "latest", "psexec": r"C:\Tools\PsExec.exe"}

    body = lg.installer_legion_work(
        "flamingo",
        whatif=True,
        run_fn=run_fn,
        credman=lambda: {},
    )
    assert seen, "WhatIf must still run the installer planner"
    assert body["whatif"] is True
    assert body["invoked_installer"] is True
    assert body.get("status") == "dry-run"
    fails = body.get("failures") or []
    assert any(f.get("error") == "credman-missing" for f in fails)
    assert "password" not in body


def test_fr5530_live_still_fails_closed_without_credman():
    def boom(spec):
        raise AssertionError("live install must not run without credman")

    body = lg.installer_legion_work(
        "flamingo",
        whatif=False,
        run_fn=boom,
        credman=lambda: {},
    )
    assert body["ok"] is False
    assert body["invoked_installer"] is False
    assert body["error"] == "credman-missing"


def test_fr5530_whatif_verb_not_exit_126(tmp_path):
    def run_fn(spec):
        return {"ok": True, "status": "dry-run"}

    res = lg.run_legion_verb(
        target="flamingo",
        whatif=True,
        job_id="aabbccdd",
        wait=True,
        worker=lambda target, **k: lg.installer_legion_work(
            target, run_fn=run_fn, credman=lambda: {}, **k
        ),
    )
    assert "exit=126" not in res.reply
    assert "LEGION accepted" in res.reply or "DONE id=aabbccdd exit=0" in res.reply
    assert any(f.get("error") == "credman-missing" for f in res.failures)


def test_fr5530_dry_run_probes_psexec_not_install_remote(monkeypatch, tmp_path):
    called = {"n": 0}

    def boom(**_kw):
        called["n"] += 1
        raise AssertionError("install_remote must not run on dry_run")

    monkeypatch.setattr("airc_network_installer.install.install_remote", boom)
    monkeypatch.setattr(
        "airc_network_installer.install.find_psexec",
        lambda _explicit="": r"C:\Tools\PsExec.exe",
    )
    msi = tmp_path / "airc-1.0.0.msi"
    msi.write_bytes(b"MZ")
    out = lg.default_installer_run(
        {
            "hosts": ["flamingo"],
            "profile": "client",
            "force": False,
            "timeout_s": 900,
            "dry_run": True,
            "msi": str(msi),
        }
    )
    assert called["n"] == 0
    assert out["status"] == "dry-run"
    assert out.get("psexec")
    assert "airc-1.0.0.msi" in str(out.get("msi") or "")
