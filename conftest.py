"""Test bootstrap (t773u): the python modules live in <service>/scripts; the shared engine is in common/scripts.
Every scripts dir goes on sys.path (as the flat staged layout has them side by side) and tests import repo_layout."""
import sys
from pathlib import Path

_repo = Path(__file__).resolve().parent
for _p in [_repo / "common" / "tests"] + [_repo / s / "scripts" for s in ("airc", "bob", "jeeves", "common")]:
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))