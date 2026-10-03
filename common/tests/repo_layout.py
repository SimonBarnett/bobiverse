"""Compat shim (FR #963): canonical ``repo_layout`` lives in ``common/scripts``.

Sparse FR/MRB worktrees often include ``common/scripts`` but omit ``common/tests``.
This file keeps older ``PYTHONPATH=common/tests`` working by loading the scripts copy.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_scripts = Path(__file__).resolve().parents[1] / "scripts"
_canon = _scripts / "repo_layout.py"
if not _canon.is_file():
    raise ImportError(
        f"FR #963: missing {_canon}. Add common/scripts to the worktree "
        "(git sparse-checkout add common/scripts) or disable sparse-checkout."
    )
_spec = importlib.util.spec_from_file_location("repo_layout", _canon)
if _spec is None or _spec.loader is None:
    raise ImportError(f"FR #963: cannot load {_canon}")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
# Replace this shim module so ``from repo_layout import REPO`` sees the canonical attrs.
sys.modules[__name__] = _mod