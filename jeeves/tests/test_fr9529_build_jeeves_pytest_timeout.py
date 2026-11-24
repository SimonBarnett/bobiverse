"""FR #9529: build-jeeves pytest must not hang unbounded (job/step timeout + per-test)."""
from __future__ import annotations

from pathlib import Path

from repo_layout import REPO

WF = REPO / ".github" / "workflows" / "build-jeeves.yml"


def test_fr9529_build_jeeves_has_job_and_pytest_timeouts():
    text = WF.read_text(encoding="utf-8")
    assert "FR #9529" in text or "9529" in text
    # Job-level GHA timeout so a stuck suite fails the run instead of sitting forever.
    assert "timeout-minutes:" in text
    # Pytest step also capped (tighter than the full job).
    assert "Pytest jeeves/tests" in text
    # Per-test guard (pytest-timeout); Windows needs thread method.
    assert "pytest-timeout" in text
    assert "--timeout=" in text or "--timeout " in text
    assert "timeout-method" in text
    # Concurrency: cancel superseded tip builds so the queue does not pile hung runners.
    assert "concurrency:" in text
    assert "cancel-in-progress" in text
