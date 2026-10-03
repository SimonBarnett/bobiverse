"""FR #963: ensure ``repo_layout`` imports without root conftest / without common/tests in sparse trees.

Canonical module: ``common/scripts/repo_layout.py`` (present when ``common/scripts`` is checked out).
"""
from __future__ import annotations

import sys
from pathlib import Path

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
