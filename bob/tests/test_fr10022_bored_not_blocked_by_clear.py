"""FR #10022: idle !bored send is not behind skill sync or Cursor Clear."""
from pathlib import Path

from repo_layout import ROOT

SRC = (ROOT / "bob" / "scripts" / "bob_worker.py").read_text(encoding="utf-8")


def test_fr10022_fire_sends_before_sync_and_sweep():
    fire = SRC.index("def _fire(self, reason: str, now: float)")
    body = SRC[fire:fire + 2500]
    assert body.index("ok = bool(self.send())") < body.index("maybe_sync_install_skills")
    assert "FR #10022" in body


def test_fr10022_idle_clear_is_opencode_only():
    sweep = SRC.index("def _idle_job_worktree_sweep")
    body = SRC[sweep:sweep + 1600]
    assert 'strip().lower() == "opencode"' in body
    assert "elif anchor" not in body
    assert "Cursor" in body
