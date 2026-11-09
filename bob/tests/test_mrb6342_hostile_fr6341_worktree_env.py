"""Hostile pins for FR #6341 / MRB #6342: seat marker + worktree env."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bob" / "scripts"))
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import bob_worker as bw  # noqa: E402


def test_mrb6342_marker_replaces_stale_and_exports_base(monkeypatch):
    with tempfile.TemporaryDirectory(prefix="mrb6342-") as raw:
        folder = Path(raw)
        (folder / ".bobiverse-seat").write_text(
            json.dumps({"nick": "old-1", "pid": 1}), encoding="utf-8"
        )
        path = bw.write_live_seat_marker(folder, nick="new-2", pid=2, machine="box")
        obj = json.loads(path.read_text(encoding="utf-8"))
        assert obj == {"nick": "new-2", "pid": 2, "machine": "box"}
        base = Path(raw) / "wt"
        monkeypatch.setenv("BOB_JOB_WORKTREE_BASE", str(base))
        monkeypatch.delenv("BOB_BRIDGE_HOME", raising=False)
        extra = bw.seat_env_extra(folder / "run", "box", "box-2")
        assert Path(extra["BOB_JOB_WORKTREE_BASE"]).is_dir()


def test_mrb6342_skill_ai_worktrees_no_bel():
    text = (
        ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "ai\\worktrees" in text
    assert "\x07" not in text
    assert "for i\\worktrees" not in text
    assert "BOB_JOB_WORKTREE_BASE" in text
    assert "FR #6341" in text
    assert "never search drives" in text
