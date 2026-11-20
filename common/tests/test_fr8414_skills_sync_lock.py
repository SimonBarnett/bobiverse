"""FR #8414: skills-sync is one-at-a-time and retries index.lock."""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

import sync_install_skills as sis


def _proc(code: int, out: str = "", err: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["git"], code, out, err)


def _install(tmp_path: Path) -> Path:
    install = tmp_path / "install"
    (install / ".git").mkdir(parents=True)
    return install


def _fake_git(state: dict):
    def _git(_install: Path, args: list[str], timeout: float = 120.0):
        if args[0] == "fetch":
            return _proc(0)
        if args[0] == "rev-parse":
            return _proc(0, "abc1234def\n")
        if args[0] == "cat-file":
            if args[-1].endswith("bob/.grok/skills"):
                return _proc(0)
            return _proc(1)
        if args[0] == "checkout":
            state["inside"] = state.get("inside", 0) + 1
            state["max"] = max(state.get("max", 0), state["inside"])
            state["checkouts"] = state.get("checkouts", 0) + 1
            n = state["checkouts"]
            time.sleep(0.1)
            state["inside"] -= 1
            if state.get("fail_first") and n == 1:
                lock = _install / ".git" / "index.lock"
                lock.write_text("stale\n", encoding="ascii")
                return _proc(1, "", "fatal: Unable to create 'index.lock': File exists.")
            return _proc(0)
        return _proc(0)

    return _git


def test_fr8414_index_lock_retries_then_ok(tmp_path: Path, monkeypatch) -> None:
    install = _install(tmp_path)
    state = {"fail_first": True}
    monkeypatch.setattr(sis, "_git", _fake_git(state))
    monkeypatch.setattr(sis, "_mirror_agent_books", lambda *a, **k: None)
    got = sis.sync_install_skills_from_origin(install, fetch=True, retry_sleeps=(0.0, 0.0))
    assert got["ok"] is True
    assert got["reason"] == "synced"
    assert got["sha"] == "abc1234def"
    assert not (install / ".git" / "index.lock").exists()
    assert state["checkouts"] == 2


def test_fr8414_overlapping_syncs_are_serialized(tmp_path: Path, monkeypatch) -> None:
    install = _install(tmp_path)
    state = {"fail_first": False}
    monkeypatch.setattr(sis, "_git", _fake_git(state))
    monkeypatch.setattr(sis, "_mirror_agent_books", lambda *a, **k: None)
    results: list[dict] = []

    def _run() -> None:
        results.append(
            sis.sync_install_skills_from_origin(install, fetch=False, retry_sleeps=(0.0,))
        )

    threads = [threading.Thread(target=_run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert len(results) == 2
    assert all(r["ok"] and r["reason"] == "synced" for r in results)
    assert state["max"] == 1
    assert sis.read_skills_sha(install) == "abc1234def"


def test_fr8414_dead_holder_drops_stale_index_lock(tmp_path: Path, monkeypatch) -> None:
    install = _install(tmp_path)
    run = install / "run"
    run.mkdir()
    (run / sis.LOCK_NAME).write_text("999999\n", encoding="ascii")
    (install / ".git" / "index.lock").write_text("killed\n", encoding="ascii")
    monkeypatch.setattr(sis, "_pid_alive", lambda pid: False)
    monkeypatch.setattr(sis, "_git", _fake_git({"fail_first": False}))
    monkeypatch.setattr(sis, "_mirror_agent_books", lambda *a, **k: None)
    got = sis.sync_install_skills_from_origin(install, fetch=False, retry_sleeps=(0.0,))
    assert got["ok"] is True
    assert not (install / ".git" / "index.lock").exists()
    assert not (run / sis.LOCK_NAME).exists()
