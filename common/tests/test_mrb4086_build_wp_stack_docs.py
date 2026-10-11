"""MRB #4086: BUILD WP stacking lesson lives in docs/bobiverse-build.md (not harvest)."""
from __future__ import annotations

from repo_layout import ROOT

DOCS = ROOT / "docs/bobiverse-build.md"
HARVEST = ROOT / "common/.grok/skills/harvest/SKILL.md"


def _utf8(p):
    raw = p.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM in {p}"
    return raw.decode("utf-8")


def test_mrb4086_build_wp_stack_lesson_in_docs_not_harvest():
    docs = _utf8(DOCS)
    assert "WP stacking (implementer)" in docs
    assert "FakeGitHubFiler" in docs
    assert "rebase WP3" in docs or "INSTALL-TEST" in docs
    # Wrong-book tip must not land the bullet in harvest process book.
    harvest = _utf8(HARVEST)
    assert "INSTALL-TEST WP3 reuses WP2 FakeGitHubFiler" not in harvest
