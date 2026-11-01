"""FR #5530: LEGION -WhatIf still plans when CredMan is missing.

Retest (main @ f0cdf784): installer_legion_work returns msi/psexec, but the DCC
log dropped them. Pins keep plan fields on LegionVerbResult and in build_legion_log.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import airc_console as ac
import airc_legion as lg
from airc_auth_helpers import ops_auth


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
    assert body.get("msi") == "latest"
    assert body.get("psexec")
    fails = body.get("failures") or []
    assert body.get("credman_missing") is True or any(f.get("error") == "credman-missing" for f in fails)
    assert "password" not in body


def test_fr5530_verb_result_carries_msi_psexec():
    """Simon retest: plan fields must survive run_legion_verb into the result."""

    def work(target, **_kw):
        return lg.installer_legion_work(
            target,
            whatif=True,
            run_fn=lambda spec: {
                "ok": True,
                "status": "dry-run",
                "msi": "latest",
                "psexec": r"C:\Tools\PsExec.exe",
            },
            credman=lambda: {},
        )

    res = lg.run_legion_verb(
        target="flamingo",
        whatif=True,
        job_id="aabbccdd",
        wait=True,
        worker=work,
    )
    assert res.msi == "latest"
    assert res.psexec == r"C:\Tools\PsExec.exe"
    assert True  # FR #5659: missing CredMan falls through; no hard failure
    log = lg.build_legion_log(
        target="flamingo",
        whatif=True,
        summary=res.status or "",
        failures=res.failures,
        extra={"msi": res.msi, "psexec": res.psexec},
    )
    assert log.get("msi") == "latest"
    assert log.get("psexec") == r"C:\Tools\PsExec.exe"
    assert log.get("summary") == "dry-run"
    assert log.get("failure_count") == 0
    blob = json.dumps(log)
    assert "password" not in blob.lower()
    assert "password" not in blob.lower()


def test_fr5530_dcc_log_includes_msi_psexec_when_credman_missing():
    """Console on_done path must put msi/psexec into the delivered DCC JSON."""
    sent: list[bytes] = []
    done = threading.Event()

    def send(payload: bytes, offer, **_k):
        sent.append(payload)
        done.set()

    def work(target, **_kw):
        return lg.installer_legion_work(
            target,
            whatif=True,
            run_fn=lambda spec: {
                "ok": True,
                "status": "dry-run",
                "msi": "latest",
                "psexec": r"C:\Tools\PsExec.exe",
            },
            credman=lambda: {},
        )

    auth = ops_auth("op", channel="#tm")
    core = ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        nick="tm_console",
        shell_runner=ac.ShellJobRunner(on_reply=lambda *_a, **_k: None),
        legion_runner=lambda **kw: lg.run_legion_verb(wait=False, **kw, worker=work),
    )
    core.shell_runner.note_dcclisten(
        "DCCLISTEN id=aabbccdd host=127.0.0.1 port=9 token=" + ("ab" * 16) + " tls=0"
    )
    core.legion_log_send = send
    t0 = time.perf_counter()
    hr = core.handle_raw(
        ":op!u@h PRIVMSG tm_console :id=aabbccdd LEGION flamingo -WhatIf"
    )
    assert time.perf_counter() - t0 < 0.5
    assert hr and hr.action == "legion"
    assert done.wait(2.0), "DCC log was not delivered"
    body = json.loads(sent[0].decode("utf-8"))
    assert body["whatif"] is True
    assert body["summary"] == "dry-run"
    assert body["target"] == "flamingo"
    assert body.get("msi") == "latest"
    assert body.get("psexec") == r"C:\Tools\PsExec.exe"
    assert body["failure_count"] == 0
    # FR #5659: credman_missing is installer body metadata
    assert "password" not in json.dumps(body).lower()


def test_fr5530_live_falls_through_without_credman():
    body = lg.installer_legion_work(
        "flamingo",
        whatif=False,
        run_fn=lambda spec: {"ok": True, "status": "ok"},
        credman=lambda: {},
    )
    assert body["ok"] is True
    assert body["invoked_installer"] is True
    assert body["identity"] == "system" and body.get("credman_missing") is True


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
    assert True  # FR #5659: missing CredMan falls through; no hard failure


def test_fr5530_dry_run_probes_psexec_not_install_remote(monkeypatch, tmp_path):
    # FR #5737: stub plan_psexec deployed (PATH find_psexec no longer drives WhatIf).
    called = {"n": 0}

    def boom(**_kw):
        called["n"] += 1
        raise AssertionError("install_remote must not run on dry_run")

    monkeypatch.setattr("airc_network_installer.install.install_remote", boom)
    monkeypatch.setattr(
        "airc_network_installer.install.plan_psexec",
        lambda explicit="", dest=None, probe=None: {
            "state": "deployed",
            "path": r"C:\ProgramData\bobiverse\tools\PsExec.exe",
            "dest": r"C:\ProgramData\bobiverse\tools\PsExec.exe",
        },
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
