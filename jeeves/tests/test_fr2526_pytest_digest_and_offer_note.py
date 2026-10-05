"""FR #2526: refuse pytest BOB_DIGEST_HOME; require_machine-all offer is note-only."""
from __future__ import annotations

import json
import os
from pathlib import Path

import jeeves_main
import jeeves_maintenance as jm


def test_fr2526_ephemeral_pytest_home_helper():
    assert jeeves_main.is_ephemeral_pytest_home(
        r"C:\Users\Administrator\AppData\Local\Temp\2\pytest-of-Administrator\pytest-179\test_x0"
    )
    assert jeeves_main.is_ephemeral_pytest_home(r"D:\tmp\pytest-current\home")
    assert not jeeves_main.is_ephemeral_pytest_home(r"C:\Users\Administrator\.bobiverse")


def test_fr2526_resolve_digest_skips_pytest_env(tmp_path, monkeypatch):
    real = tmp_path / ".bobiverse"
    real.mkdir()
    bad = tmp_path / "pytest-of-Administrator" / "pytest-1" / "h"
    bad.mkdir(parents=True)
    monkeypatch.setenv("BOB_DIGEST_HOME", str(bad))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    # no --digest-home
    got = jeeves_main.resolve_digest_home(digest_home_arg="", home_arg="")
    assert got.resolve() == real.resolve()


def test_fr2526_offer_all_require_machine_is_note_not_finding(tmp_path, monkeypatch):
    home = tmp_path / "d"
    home.mkdir()

    def fake_summarize(_root, _nick):
        return {
            "unaccepted": 4,
            "offerable": 0,
            "out_of_focus": 0,
            "require_machine": 4,
        }

    monkeypatch.setattr("gitclaim.summarize_empty_offer", fake_summarize)
    detail, findings, errors = jeeves_main._check_offer(home, None)
    assert findings == []
    assert errors == []
    assert detail.get("offer_note_only") is True
    assert "0 offerable" in str(detail.get("offer_note") or "")


def test_fr2526_offer_mixed_gates_still_finding(tmp_path, monkeypatch):
    home = tmp_path / "d"
    home.mkdir()

    def fake_summarize(_root, _nick):
        return {
            "unaccepted": 4,
            "offerable": 0,
            "out_of_focus": 2,
            "require_machine": 2,
        }

    monkeypatch.setattr("gitclaim.summarize_empty_offer", fake_summarize)
    detail, findings, errors = jeeves_main._check_offer(home, None)
    assert any("0 offerable" in f for f in findings)
    assert detail.get("ok") is False


def test_fr2526_monitor_digest_home_refuses_pytest(tmp_path, monkeypatch):
    import importlib.util

    path = Path("jeeves/tools/monitor/_common.py").resolve()
    spec = importlib.util.spec_from_file_location("mon_common2526", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    real = tmp_path / ".bobiverse"
    real.mkdir()
    bad = tmp_path / "pytest-of-Administrator" / "x"
    bad.mkdir(parents=True)
    env = {"BOB_DIGEST_HOME": str(bad), "USERPROFILE": str(tmp_path)}
    got = mod.digest_home(env)
    assert got.resolve() == real.resolve()


def test_fr2526_spawn_clears_pytest_env(tmp_path, monkeypatch):
    seen = {}

    def fake_popen(argv, cwd=None, close_fds=True, creationflags=0, env=None):
        seen["env"] = dict(env or {})

        class P:
            pid = 4242

        return P()

    monkeypatch.setattr(jm.subprocess, "Popen", fake_popen)
    monkeypatch.setenv(
        "BOB_DIGEST_HOME",
        str(tmp_path / "pytest-of-Administrator" / "h"),
    )
    exe = tmp_path / "bob-worker.exe"
    exe.write_bytes(b"MZ")
    jm._spawn_bob_worker(exe, tmp_path / "bob", tmp_path / "jeeves")
    assert "BOB_DIGEST_HOME" not in seen["env"]
