"""FR #963: ensure ``repo_layout`` imports without root conftest / without common/tests in sparse trees.

Canonical module: ``common/scripts/repo_layout.py`` (present when ``common/scripts`` is checked out).
"""
from __future__ import annotations

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


@pytest.fixture(autouse=True, scope="session")
def _fr7315_winps51_psmodulepath():
    """FR #7315: pytest under pwsh 7 must not hide 5.1 Get-FileHash from powershell.exe children."""
    import winps51

    winps51.apply_winps51_module_path(__import__("os").environ)
    yield
