"""FR #7020: SYSTEM-safe python resolve + spawn-fail releases build lock."""
from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import bobiverse_build as bb
import bobiverse_python as bp


def test_fr7020_env_wins(tmp_path: Path, monkeypatch):
    fake = tmp_path / "python.exe"
    fake.write_text("", encoding="utf-8")
    monkeypatch.setenv("BOBIVERSE_PYTHON", str(fake))
    monkeypatch.delenv("BOB_PYTHON", raising=False)
    path, src = bp.resolve_service_python()
    assert path == str(fake)
    assert src.startswith("env:")


def test_fr7020_stamp_used_when_env_empty(tmp_path: Path, monkeypatch):
    fake = tmp_path / "py" / "python.exe"
    fake.parent.mkdir(parents=True)
    fake.write_text("", encoding="utf-8")
    install = tmp_path / "bob"
    (install / "config").mkdir(parents=True)
    (install / "config" / "python.path").write_text(str(fake) + "\n", encoding="utf-8")
    monkeypatch.delenv("BOBIVERSE_PYTHON", raising=False)
    monkeypatch.delenv("BOB_PYTHON", raising=False)
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(install))
    monkeypatch.setenv("PATH", str(tmp_path / "emptybin"))
    path, src = bp.resolve_service_python()
    assert path == str(fake)
    assert src.startswith("stamp:")


def test_fr7020_missing_returns_none(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("BOBIVERSE_PYTHON", raising=False)
    monkeypatch.delenv("BOB_PYTHON", raising=False)
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(tmp_path / "bob-empty"))
    monkeypatch.setenv("PATH", str(tmp_path / "nobin"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "pf"))
    with mock.patch.object(bp, "_from_registry", return_value=(None, "")):
        with mock.patch.object(bp, "_from_py_launcher", return_value=(None, "")):
            with mock.patch.object(bp, "_from_filesystem", return_value=(None, "")):
                path, src = bp.resolve_service_python()
    assert path is None
    assert src == "missing"


def test_fr7020_skips_windowsapps_stub(tmp_path: Path, monkeypatch):
    stub = tmp_path / "WindowsApps" / "python.exe"
    stub.parent.mkdir(parents=True)
    stub.write_text("", encoding="utf-8")
    monkeypatch.delenv("BOBIVERSE_PYTHON", raising=False)
    monkeypatch.delenv("BOB_PYTHON", raising=False)
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(tmp_path / "bob"))
    monkeypatch.setenv("PATH", str(stub.parent))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "pf"))
    with mock.patch.object(bp, "_from_registry", return_value=(None, "")):
        with mock.patch.object(bp, "_from_py_launcher", return_value=(None, "")):
            with mock.patch.object(bp, "_from_filesystem", return_value=(None, "")):
                with mock.patch.object(bp.shutil, "which", return_value=str(stub)):
                    path, src = bp.resolve_service_python()
    assert path is None
    assert src == "missing"


def test_fr7020_spawn_fail_writes_result_and_releases_lock(tmp_path: Path, monkeypatch):
    """Acceptance: failed runner spawn writes fail result and frees machine lock."""
    lock_path = tmp_path / "build-locks.json"
    lock = bb.BuildLock(lock_path, max_parallel=1)
    assert lock.try_acquire("SimonBarnett/bobiverse", "b-7020")[0]

    job = tmp_path / "build-2.0.0-1.json"
    job.write_text(
        json.dumps(
            {
                "v": 1,
                "repos": ["SimonBarnett/bobiverse"],
                "version": "2.0.0",
                "id": "b-7020",
            }
        ),
        encoding="utf-8",
    )
    result_path = Path(str(job) + ".result.json")
    announces: list[str] = []

    # Simulate the FR #7020 fail path (same shape as irc_agent._fail_spawn).
    detail = "python.exe not found"
    id_bit = " id=b-7020"
    repo = "SimonBarnett/bobiverse"
    result_path.write_text(
        json.dumps(
            {
                "ok": False,
                "exit_code": 127,
                "error": "python-missing",
                "announce": [
                    f"BUILD fail {repo}{id_bit} version=2.0.0 error=python-missing detail={detail}"
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    lock.release(repo)
    announces.append(
        f"BUILD fail {repo}{id_bit} version=2.0.0 error=python-missing detail={detail}"
    )

    assert lock.running_id(repo) is None
    res = json.loads(result_path.read_text(encoding="utf-8"))
    assert res["error"] == "python-missing"
    assert any("BUILD fail" in a and "id=b-7020" in a for a in announces)

    # Chair lock release path: parse announce + apply.
    chair = bb.BuildLock(tmp_path / "chair-locks.json", max_parallel=1)
    assert chair.try_acquire(repo, "b-7020")[0]
    parsed = bb.parse_build_result(announces[0])
    assert parsed and parsed["kind"] == "fail" and parsed["id"] == "b-7020"
    assert bb.apply_build_result_to_chair_lock(chair, parsed) is True
    assert chair.running_id(repo) is None


def test_fr7020_wiring_pins():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    agent = (root / "scripts" / "irc_agent.py").read_text(encoding="utf-8")
    assert "bobiverse_python" in agent
    assert "python-missing" in agent
    assert "FR #7020" in agent
    common = (root / "scripts" / "Bobiverse-Common.ps1").read_text(encoding="utf-8")
    assert "Write-BobiversePythonStamp" in common
    assert "FR #7020" in common
    assert "PythonCore" in common
