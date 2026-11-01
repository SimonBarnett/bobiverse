"""FR #5382: default_installer_run must invoke install_remote (not status=scheduled)."""
from __future__ import annotations

from pathlib import Path

import airc_legion as lg
from airc_network_installer.core import HostResult


def test_fr5382_dry_run_still_skips_install_remote(monkeypatch, tmp_path):
    # FR #5737: WhatIf uses plan_psexec (airc-owned deploy); stub deployed so this
    # case still asserts dry-run skip of install_remote (ok=True).
    called = {"n": 0}

    def boom(**_kw):
        called["n"] += 1
        raise AssertionError("install_remote must not run on dry_run")

    monkeypatch.setattr(
        "airc_network_installer.install.plan_psexec",
        lambda explicit="", dest=None, probe=None: {
            "state": "deployed",
            "path": r"C:\ProgramData\bobiverse\tools\PsExec.exe",
            "dest": r"C:\ProgramData\bobiverse\tools\PsExec.exe",
        },
    )
    monkeypatch.setattr(
        "airc_network_installer.install.install_remote", boom
    )
    out = lg.default_installer_run(
        {
            "hosts": ["walrus"],
            "profile": "client",
            "force": False,
            "timeout_s": 900,
            "dry_run": True,
            "username": "u",
        }
    )
    assert out["ok"] is True
    assert out["status"] == "dry-run"
    assert called["n"] == 0


def test_fr5382_live_calls_install_remote_client_900_no_force(monkeypatch, tmp_path):
    msi = tmp_path / "airc-1.2.3.msi"
    msi.write_bytes(b"MZ-fake-msi")
    seen: list[dict] = []

    def fake_remote(**kw):
        seen.append(kw)
        return HostResult(
            host=kw["host"],
            action="install",
            status="success",
            previous_version="1.0.0",
            duration_s=1.5,
            detail="ok",
        )

    monkeypatch.setenv("AIRC_LEGION_PASSWORD", "FAKE_" + "legion_env_pw")
    monkeypatch.setattr(
        "airc_network_installer.install.install_remote", fake_remote
    )
    monkeypatch.setattr(
        "airc_network_installer.install.find_psexec", lambda _explicit="": r"C:\Tools\PsExec.exe"
    )
    monkeypatch.setattr(
        "airc_network_installer.install.ensure_psexec",
        lambda _explicit="", dest=None: r"C:\Tools\PsExec.exe",
    )
    out = lg.default_installer_run(
        {
            "hosts": ["10.0.0.8"],
            "profile": "client",
            "force": False,
            "timeout_s": 900,
            "dry_run": False,
            "msi": str(msi),
            "username": r"wonderland\legion",
            "log_dir": str(tmp_path / "logs"),
            "password_via": "secure-env",
        }
    )
    assert out["ok"] is True
    assert out["status"] == "success"
    assert out.get("status") != "scheduled"
    assert "password" not in out
    assert "FAKE_legion_env_pw" not in str(out)
    assert len(seen) == 1
    kw = seen[0]
    assert kw["host"] == "10.0.0.8"
    assert kw["profile"] == "client"
    assert kw["force"] is False
    assert kw["timeout_s"] == 900.0
    assert kw["password"] == "FAKE_legion_env_pw"
    assert kw["username"] == r"wonderland\legion"
    assert kw["dry_run"] is False
    assert Path(kw["msi_path"]) == msi
    assert kw["candidate_version"] == "1.2.3"
    assert kw["psexec"].lower().endswith("psexec.exe")


def test_fr5382_missing_psexec_fails_closed(monkeypatch, tmp_path):
    # FR #5655: live path uses ensure_psexec (may download / ProgramData).
    # Stub both find + ensure and opt out of download so missing stays closed.
    msi = tmp_path / "airc-9.9.9.msi"
    msi.write_bytes(b"x")
    monkeypatch.setenv("AIRC_LEGION_PASSWORD", "FAKE_x")
    monkeypatch.setenv("AIRC_LEGION_NO_PSEXEC_DOWNLOAD", "1")
    monkeypatch.setattr(
        "airc_network_installer.install.find_psexec", lambda _explicit="": None
    )
    monkeypatch.setattr(
        "airc_network_installer.install.ensure_psexec",
        lambda _explicit="", dest=None: None,
    )
    monkeypatch.setattr(
        "airc_network_installer.install.install_remote",
        lambda **_k: (_ for _ in ()).throw(AssertionError("no call")),
    )
    out = lg.default_installer_run(
        {
            "hosts": ["box1"],
            "profile": "client",
            "force": False,
            "timeout_s": 900,
            "dry_run": False,
            "msi": str(msi),
            "username": "u",
            "log_dir": str(tmp_path / "logs"),
        }
    )
    assert out["ok"] is False
    assert "psexec" in (out.get("error") or "").lower()
