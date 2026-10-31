"""FR #5523: PRIORITY form walk fixture + worker paths work in frozen airc.exe layout."""
from __future__ import annotations

import json
from pathlib import Path

import airc_console as ac
import airc_priority as ap
from repo_layout import ROOT


def _stage_pack_layout(root: Path) -> Path:
    """Pack layout: C:\\ai\\airc\\airc\\priority-worker (FR #5283)."""
    pw = root / "airc" / "priority-worker"
    fix = pw / "fixtures"
    fix.mkdir(parents=True)
    src = ROOT / "airc" / "priority-worker" / "fixtures" / "form_walk.json"
    (fix / "form_walk.json").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    (pw / "priority_worker.py").write_text("# fixture worker\nWORKER = True\n", encoding="utf-8")
    return pw


def test_fr5523_default_fixture_uses_airc_nested_pack(tmp_path, monkeypatch):
    monkeypatch.delenv("AIRC_INSTALL_ROOT", raising=False)
    _stage_pack_layout(tmp_path)
    monkeypatch.setenv("AIRC_INSTALL_ROOT", str(tmp_path))
    p = ap.default_fixture_path()
    assert p.is_file()
    assert p.as_posix().endswith("airc/priority-worker/fixtures/form_walk.json") or (
        "airc" in p.parts and "priority-worker" in p.parts
    )


def test_fr5523_frozen_exe_parent_airc_dir(tmp_path, monkeypatch):
    """Onefile: __file__ is _MEIPASS; install is sys.executable parent tree."""
    _stage_pack_layout(tmp_path)
    exe = tmp_path / "airc" / "airc.exe"
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"MZ")
    monkeypatch.delenv("AIRC_INSTALL_ROOT", raising=False)
    monkeypatch.setattr(ap.sys, "frozen", True, raising=False)
    monkeypatch.setattr(ap.sys, "executable", str(exe))
    monkeypatch.setattr(ap.sys, "_MEIPASS", str(tmp_path / "_MEIXXXX"), raising=False)
    p = ap.default_fixture_path()
    assert p.is_file(), p
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "forms" in data


def test_fr5523_load_priority_worker_nested(tmp_path, monkeypatch):
    _stage_pack_layout(tmp_path)
    monkeypatch.setenv("AIRC_INSTALL_ROOT", str(tmp_path))
    mod = ac._load_priority_worker()
    assert mod is not None
    assert getattr(mod, "WORKER", False) is True


def test_fr5523_pins():
    src = (ROOT / "airc" / "scripts" / "airc_priority.py").read_text(encoding="utf-8")
    assert "FR #5523" in src
    assert "airc" in src and "priority-worker" in src
    assert "resolve_priority_worker_dir" in src
    con = (ROOT / "airc" / "scripts" / "airc_console.py").read_text(encoding="utf-8")
    assert "FR #5523" in con or "resolve_priority_worker_dir" in con
    assert not (ROOT / "airc" / "scripts" / "airc_priority.py").read_bytes().startswith(b"\xef\xbb\xbf")
