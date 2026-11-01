"""FR #5744: LEGION classifies unreachable targets (host_down / auth / session) with step+detail."""
from __future__ import annotations

from pathlib import Path

import airc_legion as lg
import airc_network_installer.install as inst
from airc_network_installer.core import HostResult


def _winerr(code: int, msg: str) -> OSError:
    exc = OSError(msg)
    exc.winerror = code  # type: ignore[attr-defined]
    return exc


def test_fr5744_classify_host_down_53():
    out = inst.classify_legion_install_error(
        _winerr(53, "[WinError 53] The network path was not found"),
        step="ipc",
    )
    assert out["error"] == "host_down"
    assert out["step"] == "ipc"
    assert "53" in out["detail"]
    assert "password" not in out["detail"].lower()


def test_fr5744_classify_host_down_67():
    out = inst.classify_legion_install_error(
        _winerr(67, "[WinError 67] The network name cannot be found"),
        step="copy",
    )
    assert out["error"] == "host_down"
    assert out["step"] == "copy"


def test_fr5744_classify_auth_failed_1326():
    out = inst.classify_legion_install_error(
        _winerr(1326, "[WinError 1326] Logon failure: unknown user name or bad password"),
        step="ipc",
    )
    assert out["error"] == "auth_failed"
    assert "password" not in out["detail"].lower() or "bad password" in out["detail"].lower()
    # sanitised: never echo a credential value
    assert "FAKE_" not in out["detail"]
    assert "secret" not in out["detail"].lower()


def test_fr5744_classify_session_conflict_1219():
    out = inst.classify_legion_install_error(
        _winerr(1219, "[WinError 1219] Multiple connections to a server"),
        step="ipc",
    )
    assert out["error"] == "session_conflict"
    assert out["step"] == "ipc"


def test_fr5744_classify_strips_password_token():
    exc = _winerr(5, "Access is denied for user=u password=FAKE_should_not_leak")
    out = inst.classify_legion_install_error(exc, step="ipc")
    assert out["error"] == "auth_failed"
    assert "FAKE_should_not_leak" not in out["detail"]
    assert "password=" not in out["detail"].lower()


def test_fr5744_smb_preflight_host_down_skips_remote(monkeypatch, tmp_path):
    msi = tmp_path / "airc-1.2.3.msi"
    msi.write_bytes(b"MZ-fake")
    called = {"remote": 0, "version": 0}

    monkeypatch.setattr(inst, "is_windows_smb_host", lambda host, timeout=0.4: False)
    monkeypatch.setattr(
        inst,
        "read_remote_version",
        lambda host: called.__setitem__("version", called["version"] + 1) or "",
    )

    def boom(**_kw):
        called["remote"] += 1
        raise AssertionError("install_remote body must not run after SMB preflight fail")

    # install_remote itself should preflight; call it directly
    row = inst.install_remote(
        host="flamingo",
        msi_path=msi,
        candidate_version="1.2.3",
        profile="client",
        force=False,
        psexec=r"C:\Tools\PsExec.exe",
        username="u",
        password="FAKE_x",
        log_dir=tmp_path / "logs",
        dry_run=False,
    )
    assert isinstance(row, HostResult)
    assert row.status == "failed"
    assert row.error == "host_down"
    assert row.step == "preflight"
    assert "445" in (row.detail or "") or "smb" in (row.detail or "").lower()
    assert "FAKE_x" not in (row.detail or "")
    assert called["version"] == 0


def test_fr5744_legion_exception_classifies_file_not_found(monkeypatch, tmp_path):
    msi = tmp_path / "airc-9.9.9.msi"
    msi.write_bytes(b"MZ")

    def boom(**_kw):
        raise _winerr(53, "[WinError 53] The network path was not found")

    # Non-local host: local hostname would take install_local and skip the patch.
    monkeypatch.setattr(
        "airc_network_installer.install.ensure_psexec",
        lambda explicit="", dest=None: r"C:\Tools\PsExec.exe",
    )
    monkeypatch.setattr("airc_network_installer.install.install_remote", boom)
    monkeypatch.setattr(lg, "_resolve_legion_msi_path", lambda spec: msi)

    out = lg.default_installer_run(
        {
            "hosts": ["10.0.0.8"],
            "dry_run": False,
            "profile": "client",
            "force": False,
            "timeout_s": 30,
            "msi": str(msi),
            "username": "wonderland\\admin",
        },
        secret="FAKE_legion_pw",
    )
    assert out["ok"] is False
    assert out["error"] == "host_down"
    assert "FileNotFoundError" not in str(out.get("error") or "")
    assert "install:FileNotFoundError" not in str(out)
    fails = out.get("failures") or []
    assert fails and fails[0]["error"] == "host_down"
    assert fails[0].get("step")
    assert "FAKE_legion_pw" not in str(out)
    assert "FAKE_legion_pw" not in str(fails)


def test_fr5744_legion_uses_hostresult_error_fields(monkeypatch, tmp_path):
    msi = tmp_path / "airc-1.0.0.msi"
    msi.write_bytes(b"MZ")

    def fake_remote(**_kw):
        return HostResult(
            host="10.0.0.8",
            action="install",
            status="failed",
            detail="[WinError 53] The network path was not found",
            error="host_down",
            step="copy",
        )

    monkeypatch.setattr(
        "airc_network_installer.install.ensure_psexec",
        lambda explicit="", dest=None: r"C:\Tools\PsExec.exe",
    )
    monkeypatch.setattr("airc_network_installer.install.install_remote", fake_remote)
    monkeypatch.setattr(lg, "_resolve_legion_msi_path", lambda spec: msi)

    out = lg.default_installer_run(
        {
            "hosts": ["10.0.0.8"],
            "dry_run": False,
            "profile": "client",
            "force": False,
            "timeout_s": 30,
            "msi": str(msi),
        },
        secret="",
    )
    assert out["ok"] is False
    assert out["error"] == "host_down"
    fails = out.get("failures") or []
    assert fails and fails[0]["error"] == "host_down"
    assert fails[0].get("step") == "copy"


def test_fr5744_skills_mention_host_down():
    root = Path(__file__).resolve().parents[1]
    blob = (root / ".grok/skills/bobiverse-airc-troubleshooting/SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "5744" in blob or "host_down" in blob
    assert "LEGION" in blob
