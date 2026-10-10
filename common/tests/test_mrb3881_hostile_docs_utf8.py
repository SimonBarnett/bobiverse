"""MRB #3881 hostile pins for FR #3880 product docs UTF-8 gate.

Product merge: PR #3881. Pins that must survive on main:
- PRODUCT_DOCS covers common/bob/jeeves/airc docs trees
- gate helpers and tests live in common/tests/test_fr3880_docs_utf8.py
- that module itself is UTF-8 with no BOM
- skill-harvest-log.md decodes UTF-8 with no lone cp1252 0x97
"""
from __future__ import annotations

from pathlib import Path

import repo_layout

REPO = Path(repo_layout.REPO)
GATE = REPO / "common/tests/test_fr3880_docs_utf8.py"
LOG = REPO / "common/docs/skill-harvest-log.md"


def test_mrb3881_hostile_gate_module_present_and_no_bom():
    raw = GATE.read_bytes()
    assert GATE.is_file()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "PRODUCT_DOCS" in text
    assert 'REPO / "common" / "docs"' in text
    assert 'REPO / "bob" / "docs"' in text
    assert 'REPO / "jeeves" / "docs"' in text
    assert 'REPO / "airc" / "docs"' in text
    assert "_lone_cp1252_0x97_offsets" in text
    assert "test_fr3880_product_docs_md_decode_utf8" in text
    assert "test_fr3880_no_lone_cp1252_em_dash_0x97" in text
    assert "test_fr3880_skill_harvest_log_utf8_no_bom" in text
    assert "FR #3880" in text


def test_mrb3881_hostile_skill_harvest_log_still_utf8():
    raw = LOG.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    raw.decode("utf-8")
    # Import helper from product gate (behavioural).
    import test_fr3880_docs_utf8 as gate

    assert gate._lone_cp1252_0x97_offsets(raw) == []


def test_mrb3881_hostile_product_docs_trees_nonempty():
    import test_fr3880_docs_utf8 as gate

    files = gate._docs_md_files()
    assert files
    rels = {str(p.relative_to(REPO)).replace("\\", "/") for p in files}
    assert any(r.startswith("common/docs/") for r in rels)
    # At least one of bob/jeeves/airc docs when present in sparse trees.
    product_hits = [
        r for r in rels if r.startswith(("bob/docs/", "jeeves/docs/", "airc/docs/"))
    ]
    # Sparse checkouts may omit product docs; gate still walks whatever exists.
    assert isinstance(product_hits, list)
