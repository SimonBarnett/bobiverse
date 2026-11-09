"""FR #6341: rewrite stale .bobiverse-seat at startup; export BOB_JOB_WORKTREE_BASE."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bob" / "scripts"))
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import bob_worker as bw  # noqa: E402


def test_write_live_seat_marker_replaces_stale():
    with tempfile.TemporaryDirectory(prefix="fr6341-seat-") as raw:
        folder = Path(raw)
        stale = folder / ".bobiverse-seat"
        stale.write_text(
            json.dumps({"nick": "marchhare-35252", "pid": 11256, "issue": 341}),
            encoding="utf-8",
        )
        path = bw.write_live_seat_marker(
            folder, nick="marchhare-9988", pid=9988, machine="marchhare"
        )
        assert path == stale
        obj = json.loads(path.read_text(encoding="utf-8"))
        assert obj["nick"] == "marchhare-9988"
        assert obj["pid"] == 9988
        assert obj["machine"] == "marchhare"
        assert "issue" not in obj  # fresh seat marker is live nick/pid only


def test_write_live_seat_marker_atomic_no_tmp_left():
    with tempfile.TemporaryDirectory(prefix="fr6341-atom-") as raw:
        folder = Path(raw)
        bw.write_live_seat_marker(folder, nick="flamingo-1", pid=1)
        leftovers = list(folder.glob(".bobiverse-seat.*.tmp"))
        assert leftovers == []


def test_resolve_and_ensure_job_worktree_base_creates_dir(monkeypatch):
    with tempfile.TemporaryDirectory(prefix="fr6341-base-") as raw:
        base = Path(raw) / "ai" / "worktrees"
        monkeypatch.setenv("BOB_JOB_WORKTREE_BASE", str(base))
        monkeypatch.delenv("BOB_BRIDGE_HOME", raising=False)
        got = bw.resolve_and_ensure_job_worktree_base()
        assert Path(got) == base.resolve() or Path(got) == base
        assert Path(got).is_dir()


def test_seat_env_extra_exports_worktree_base(monkeypatch):
    with tempfile.TemporaryDirectory(prefix="fr6341-env-") as raw:
        base = Path(raw) / "worktrees"
        monkeypatch.setenv("BOB_JOB_WORKTREE_BASE", str(base))
        monkeypatch.delenv("BOB_BRIDGE_HOME", raising=False)
        monkeypatch.delenv("BOB_JOB_WORKTREE", raising=False)
        extra = bw.seat_env_extra(Path(raw) / "run", "flamingo", "flamingo-45296")
        assert extra["BOB_OUTBOX"].endswith("outbox.txt")
        assert "BOB_JOB_WORKTREE_BASE" in extra
        assert Path(extra["BOB_JOB_WORKTREE_BASE"]).is_dir()
        assert "BOB_JOB_WORKTREE" not in extra
        monkeypatch.setenv("BOB_JOB_WORKTREE", str(Path(raw) / "job"))
        extra2 = bw.seat_env_extra(Path(raw) / "run", "flamingo", "flamingo-45296")
        assert extra2["BOB_JOB_WORKTREE"] == str(Path(raw) / "job")


def test_worker_prompt_names_env_and_ps51_depth():
    prompt = bw.worker_prompt(r"C:\ai\bob\worker", r"C:\run", "flamingo", "flamingo-1")
    assert "BOB_JOB_WORKTREE_BASE" in prompt
    assert "BOB_JOB_WORKTREE" in prompt
    assert "PowerShell 5.1" in prompt
    assert "-Depth" in prompt
    assert "-MaxDepth" in prompt


def _skill_text(*parts: str) -> str:
    path = ROOT.joinpath(*parts)
    assert path.is_file(), path
    return path.read_text(encoding="utf-8")


def test_docs_pin_fr6341_phrases():
    worker = _skill_text("bob", ".grok", "skills", "bobiverse-bob-worker", "SKILL.md")
    irc = _skill_text("bob", ".grok", "skills", "bobiverse-bob-job-irc", "SKILL.md")
    seat = _skill_text(
        "bob", "agents", "worker", ".grok", "skills", "bobiverse-worker-seat", "SKILL.md"
    )
    for text, label in ((worker, "bob-worker"), (irc, "job-irc"), (seat, "worker-seat")):
        assert "BOB_JOB_WORKTREE_BASE" in text, label
        assert "BOB_JOB_WORKTREE" in text, label
        assert ".bobiverse-seat" in text, label
        assert "PowerShell 5.1" in text or "Windows PowerShell 5.1" in text, label
        assert "-Depth" in text, label
        assert "FR #6341" in text, label
