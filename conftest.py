"""Test bootstrap (t773u / FR #963): python modules live in <service>/scripts; shared engine in common/scripts.
Every scripts dir goes on sys.path (flat staged layout). ``repo_layout`` lives in ``common/scripts`` so sparse
FR/MRB trees that include ``common/scripts`` (but omit ``common/tests``) still collect tests.
``common/tests`` stays on the path for any remaining test-only helpers.
FR #5422: wrap pytest cleanup_dead_symlinks so WinError 5 on pytest-current is not a session fail.
"""
import sys
from pathlib import Path

_repo = Path(__file__).resolve().parent
for _p in [_repo / s / "scripts" for s in ("airc", "bob", "jeeves", "common")] + [_repo / "common" / "tests"]:
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def pytest_configure(config):
    try:
        import crash_report
        import _pytest.pathlib as _pl
        import _pytest.tmpdir as _td

        _pl.cleanup_dead_symlinks = crash_report.wrap_cleanup_dead_symlinks(_pl.cleanup_dead_symlinks)
        _td.cleanup_dead_symlinks = crash_report.wrap_cleanup_dead_symlinks(_td.cleanup_dead_symlinks)
    except Exception:
        return