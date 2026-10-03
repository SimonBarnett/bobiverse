"""FR #602: canonical open-issues map exists and names protected + core canonicals."""
from pathlib import Path

from repo_layout import ROOT

DOC = Path(ROOT / "docs" / "open-issues-canonical.md")


def test_open_issues_canonical_doc_exists_and_lists_protected():
    assert DOC.is_file(), "docs/open-issues-canonical.md missing"
    text = DOC.read_text(encoding="utf-8")
    for needle in ("#118", "#153", "#161", "#232", "#298", "#287", "#296", "#315", "#247", "#265", "#595", "#602"):
        assert needle in text, f"missing {needle}"