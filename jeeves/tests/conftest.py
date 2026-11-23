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


# ---------------------------------------------------------------------------
# FR #9382 pytest allowlist for synthetic UAT repos
#
# Production chair skips UAT when ``uat_release.repo_has_release_to_build`` is
# false (customer/plan-only repos). Legacy jeeves tests enqueue/offer UAT for
# short synthetic names like ``o/a``. Autouse below extends
# ``BOB_UAT_RELEASE_REPOS`` so those suites keep testing UAT gates; denial
# coverage stays on real non-release names (wetherby / obw) in
# ``test_fr9382_uat_release_to_build_only.py``.
# ---------------------------------------------------------------------------
import os

import pytest

# Short synthetic owner/name pairs used across jeeves UAT offer/enqueue tests.
_FR9382_SYNTHETIC_UAT_REPOS = (
    "o/a,o/b,o/c,o/d,o/q,o/r,o/y,o/z,a/b,other/x,other/tool,noise/repo,Own/bob,pull/7"
)


@pytest.fixture(autouse=True)
def _fr9382_allow_synthetic_uat_repos(monkeypatch):
    """Ensure synthetic test repos remain release-eligible under FR #9382."""
    import uat_release

    cur = (os.environ.get(uat_release.UAT_RELEASE_REPOS_ENV) or "").strip()
    parts = [p.strip() for p in cur.replace(";", ",").split(",") if p.strip()]
    for piece in _FR9382_SYNTHETIC_UAT_REPOS.split(","):
        if piece and piece not in parts:
            parts.append(piece)
    monkeypatch.setenv(uat_release.UAT_RELEASE_REPOS_ENV, ",".join(parts))

