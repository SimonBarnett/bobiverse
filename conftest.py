"""Test bootstrap (t773u / FR #963): python modules live in <service>/scripts; shared engine in common/scripts.
Every scripts dir goes on sys.path (flat staged layout). ``repo_layout`` lives in ``common/scripts`` so sparse
FR/MRB trees that include ``common/scripts`` (but omit ``common/tests``) still collect tests.
``common/tests`` stays on the path for any remaining test-only helpers.
"""
import sys
from pathlib import Path

_repo = Path(__file__).resolve().parent
for _p in [_repo / s / "scripts" for s in ("airc", "bob", "jeeves", "common")] + [_repo / "common" / "tests"]:
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))