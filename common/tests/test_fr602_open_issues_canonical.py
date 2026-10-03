"""FR #602 / MRB #607: canonical open-issues map exists and names protected + core canonicals."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

DOC = Path(ROOT / "docs" / "open-issues-canonical.md")

PROTECTED = ("#118", "#153", "#161", "#232")
CANONICALS = ("#298", "#287", "#296", "#315", "#247", "#265", "#593", "#587", "#595", "#269", "#285", "#224", "#602")


def test_open_issues_canonical_doc_exists_and_lists_protected():
    assert DOC.is_file(), "docs/open-issues-canonical.md missing"
    raw = DOC.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "doc must be UTF-8 without BOM"
    text = raw.decode("utf-8")
    assert len(text) > 400, "canonical map looks stubby"
    assert "## Protected" in text
    assert "## Canonicals" in text
    assert "## Policy for new intake" in text
    for needle in PROTECTED + ("#298", "#287", "#296", "#315", "#247", "#265", "#595", "#602"):
        assert needle in text, f"missing {needle}"


def test_canonical_map_lists_each_topic_id():
    text = DOC.read_text(encoding="utf-8")
    for needle in CANONICALS:
        assert needle in text, f"missing canonical {needle}"


def test_already_fixed_mentions_shipped_prs():
    text = DOC.read_text(encoding="utf-8")
    assert "PR #271" in text or "#271" in text
    assert "#258" in text
