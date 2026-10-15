"""FR #963 path bootstrap + FR #4315 digest-home isolation for common/tests.

When ``BOBIVERSE_BUILD_SUITE`` is set (!build #4183), ``bob_home._admin_profile`` already
redirects to USERPROFILE. This autouse fixture still pins ``BOB_DIGEST_HOME`` /
``BOB_HOME`` to a per-test tmp dir whenever the caller has not set them, so a local
``pytest common/tests`` on a box with a live ``~/.bobiverse`` cannot rewrite queue.json.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_repo = Path(__file__).resolve().parents[2]
for _p in (
    _repo / "common" / "scripts",
    _repo / "common" / "tests",
    _repo / "airc" / "scripts",
    _repo / "bob" / "scripts",
    _repo / "jeeves" / "scripts",
):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


@pytest.fixture(autouse=True)
def _fr4315_isolate_digest_home(tmp_path_factory, monkeypatch):
    """Pin digest/chair homes away from the operator profile when unset."""
    if (os.environ.get("BOB_DIGEST_HOME") or "").strip():
        # !build / an explicit test already redirected — leave alone.
        yield
        return
    root = tmp_path_factory.mktemp("fr4315-digest")
    digest = root / ".bobiverse"
    chair = root / ".jeeves"
    digest.mkdir(parents=True)
    chair.mkdir(parents=True)
    monkeypatch.setenv("BOB_DIGEST_HOME", str(digest))
    monkeypatch.setenv("BOB_HOME", str(chair))
    yield
