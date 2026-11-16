"""FR #7910: the worker build must ship scripts it launches by path."""
from __future__ import annotations

from pathlib import Path

import worker_shipped_scripts as ship

from repo_layout import ROOT

WORKER = ROOT / "bob" / "scripts" / "bob_worker.py"
BUILD = ROOT / "bob" / "scripts" / "Build-BobWorker.ps1"
WF = ROOT / ".github" / "workflows" / "build-bob-worker.yml"
PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
DOCS = ROOT / "bob" / "docs" / "bob-worker.md"


def test_fr7910_enumerates_by_path_scripts():
    names = ship.by_path_script_names(WORKER.read_text(encoding="utf-8"))
    assert "opencode_tool_wedge.py" in names
    assert "opencode_turn_guard.py" in names
    for name in names:
        assert (ROOT / "bob" / "scripts" / name).is_file(), name


def test_fr7910_copy_and_check(tmp_path: Path):
    dest = tmp_path / "scripts"
    names = ship.copy_by_path_scripts(WORKER, WORKER.parent, dest)
    assert ship.check_by_path_scripts(WORKER, dest) == names
    assert (dest / "opencode_tool_wedge.py").is_file()
    assert (dest / "opencode_turn_guard.py").is_file()


def test_fr7910_check_fails_when_artifact_omits_a_script(tmp_path: Path):
    dest = tmp_path / "scripts"
    ship.copy_by_path_scripts(WORKER, WORKER.parent, dest)
    (dest / "opencode_tool_wedge.py").unlink()
    try:
        ship.check_by_path_scripts(WORKER, dest)
    except SystemExit as exc:
        assert "opencode_tool_wedge.py" in str(exc)
    else:
        raise AssertionError("check must fail when a by-path script is absent")


def test_fr7910_extract_writes_beside_exe(tmp_path, monkeypatch):
    bundle = tmp_path / "mei" / ship.BUNDLE_DIR_NAME
    bundle.mkdir(parents=True)
    (bundle / "opencode_tool_wedge.py").write_text("print('wedge')\n", encoding="utf-8")
    exe_dir = tmp_path / "worker"
    exe_dir.mkdir()
    exe = exe_dir / "bob-worker.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setattr(ship.sys, "frozen", True, raising=False)
    monkeypatch.setattr(ship.sys, "_MEIPASS", str(tmp_path / "mei"), raising=False)
    monkeypatch.setattr(ship.sys, "executable", str(exe))
    written = ship.extract_bundled_scripts()
    assert written == ["opencode_tool_wedge.py"]
    assert (exe_dir / "scripts" / "opencode_tool_wedge.py").read_text(encoding="utf-8") == "print('wedge')\n"


def test_fr7910_build_and_ci_require_the_scripts():
    build = BUILD.read_text(encoding="utf-8")
    assert "worker_shipped_scripts.py" in build
    assert "worker-scripts" in build
    wf = WF.read_text(encoding="utf-8")
    assert "worker_shipped_scripts.py" in wf
    assert "by-path scripts missing from bob-worker artifact" in wf
    assert "opencode_tool_wedge.py" in wf
    assert "opencode_turn_guard.py" in wf
    pack = PACK.read_text(encoding="utf-8")
    assert "worker\\scripts" in pack
    docs = DOCS.read_text(encoding="utf-8")
    assert "FR #7910" in docs
    assert "worker\\scripts" in docs or "worker/scripts" in docs
