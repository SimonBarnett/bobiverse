"""FR #10105: new Digest parents are created with ``hold`` by default.

Operator rule: digests start held; unhold releases children. The filing
procedure must add ``hold`` at create time, not only when parking a batch.
"""
from __future__ import annotations

from repo_layout import ROOT

FR_FILING = ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-agent-fr-filing" / "SKILL.md"


def _text() -> str:
    return FR_FILING.read_text(encoding="utf-8-sig")


def test_fr10105_digest_parent_labels_include_hold_by_default():
    t = _text()
    assert "labels `feature-request` + `fr-digest` + `hold`" in t


def test_fr10105_optional_hold_wording_removed():
    t = _text()
    assert "add `hold` only to park the whole batch" not in t


def test_fr10105_wire_order_adds_hold_with_fr_digest():
    t = _text()
    assert "add `fr-digest` + `hold` with `gh`" in t
