"""FR #7117: SYSTEM recycleseat must diagnose digest read failures and not crash."""
from __future__ import annotations

import json
import os
from pathlib import Path

import bobreport
import recycleseat as rs
import startworker as sw

NOW = 1_800_000_100.0
SEAT = "redqueen-7376"


def _isolate(monkeypatch) -> None:
    monkeypatch.setenv("BOBIVERSE_BUILD_SUITE", "1")
    monkeypatch.delenv("BOB_DIGEST_HOME", raising=False)


def _alive(install: Path) -> None:
    adir = sw.queue_dir(install)
    adir.mkdir(parents=True)
    for name in (sw.ALIVE_FILE, sw.ENGINE_ALIVE_FILE):
        path = adir / name
        path.write_text("alive")
        os.utime(path, (NOW, NOW))


def _ask(install, home, **kw):
    args = dict(
        body=f"!recycleseat {SEAT} redqueen",
        nick="Jeeves",
        account=None,
        channel="#redqueen",
        local_machine="redqueen",
        qdir=rs.queue_dir(install),
        install_root=install,
        home=home,
        machine_of_nick=bobreport.machine_from_nick,
        now=NOW,
    )
    args.update(kw)
    return rs.decide(**args)


def test_fr7117_permission_error_retries_install_digest(tmp_path, monkeypatch):
    _isolate(monkeypatch)
    install = tmp_path / "install"
    home = tmp_path / "blocked"
    home.mkdir()
    alt = install / "home"
    alt.mkdir(parents=True)
    _alive(install)
    bobreport.save_digest(
        alt,
        {"machines": {"redqueen": {"workers": {"7376": {"working_on": ""}}}}},
    )

    real_read = Path.read_text

    def guarded(self, *a, **k):
        if self == bobreport.digest_path(bobreport.fleet_digest_home(home)):
            raise PermissionError(13, "Access is denied", str(self))
        return real_read(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", guarded)
    d = _ask(install, home)
    assert d.ok, d
    assert list(rs.queue_dir(install).glob("req-*.json"))


def test_fr7117_permission_error_all_paths_diagnoses_not_crash(tmp_path, monkeypatch):
    _isolate(monkeypatch)
    install = tmp_path / "install"
    home = tmp_path / "home"
    home.mkdir()
    _alive(install)
    bobreport.save_digest(home, {"machines": {"redqueen": {"workers": {}}}})

    real_read = Path.read_text

    def boom(self, *a, **k):
        if str(self).replace("\\", "/").endswith("digest.json"):
            raise PermissionError(13, "Access is denied", str(self))
        return real_read(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", boom)
    d = _ask(install, home)
    assert not d.ok
    assert d.reason == "state_unavailable"
    assert "PermissionError" in d.line
    assert SEAT in d.line
    assert not list(rs.queue_dir(install).glob("req-*.json"))


def test_fr7117_busy_never_recycles_without_handback(tmp_path, monkeypatch):
    _isolate(monkeypatch)
    install = tmp_path / "install"
    home = tmp_path / "home"
    home.mkdir()
    (home / "registered-machines.json").write_text(
        json.dumps({"machines": ["redqueen"]}), encoding="utf-8"
    )
    _alive(install)
    bobreport.save_digest(
        home,
        {
            "machines": {
                "redqueen": {
                    "workers": {"7376": {"working_on": "MRB SimonBarnett/bobiverse#6935"}},
                    "worker_list": [
                        {"nick": SEAT, "state": "doing", "work": "MRB SimonBarnett/bobiverse#6935"}
                    ],
                }
            }
        },
    )
    d = _ask(install, home)
    assert not d.ok and d.reason == "busy"
    assert "hand back" in d.line.lower()
    assert not list(rs.queue_dir(install).glob("req-*.json"))


def test_fr7117_no_pause_on_recycle_paths():
    root = Path(__file__).resolve().parents[2]
    files = [
        root / "bob" / "tray" / "tools" / "BobTrayRecycleSeat.ps1",
        root / "common" / "scripts" / "recycleseat.py",
        root / "common" / "scripts" / "bob_recycle.py",
    ]
    banned = ("Read-Host", "pause", "Press any key", "cmd /c pause")
    for p in files:
        text = p.read_text(encoding="utf-8")
        for needle in banned:
            assert needle.lower() not in text.lower(), (p.name, needle)


def test_fr7117_sync_status_surfaces_dirty_recycle_scripts(tmp_path, monkeypatch):
    import sync_ff_stall as sff

    monkeypatch.setenv("BOB_SYNC_STATUS_DIR", str(tmp_path))
    monkeypatch.setenv(
        "BOB_SYNC_DIRTY_PATHS",
        "common/scripts/recycleseat.py,README.md",
    )
    path = sff.write_sync_status(behind=1, reason="dirty", ok=False, install_root=None)
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert "common/scripts/recycleseat.py" in doc.get("recycle_scripts_dirty")
    assert "recycle-scripts-dirty" in doc.get("sync")


def test_fr7117_dirty_recycle_scripts_flag():
    names = [
        "bob/tray/tools/BobTrayRecycleSeat.ps1",
        "README.md",
        "common/scripts/gitclaim.py",
    ]
    got = rs.dirty_recycle_script_paths(names)
    assert "bob/tray/tools/BobTrayRecycleSeat.ps1" in got
    assert "common/scripts/gitclaim.py" in got
    assert "README.md" not in got
