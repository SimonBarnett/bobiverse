"""MRB #5565 hostile pins: PUT via=dcc uses DCC_BULK_SIZE_CAP (FR #5536)."""
from __future__ import annotations

import airc_dcc_bulk as dcc
import airc_jobs as jobs
from repo_layout import ROOT


def test_mrb5565_put_max_bytes_helpers():
    assert jobs.put_max_bytes("") == jobs.MAX_PUT_BYTES == 256 * 1024
    assert jobs.put_max_bytes("IRC") == jobs.MAX_PUT_BYTES
    assert jobs.put_max_bytes("dcc") == dcc.DCC_BULK_SIZE_CAP == 2 * 1024 * 1024
    assert jobs.put_max_bytes("DCC") == dcc.DCC_BULK_SIZE_CAP


def test_mrb5565_source_and_docs_pins():
    src = (ROOT / "airc" / "scripts" / "airc_jobs.py").read_text(encoding="utf-8")
    assert "def put_max_bytes" in src
    assert "FR #5536" in src
    assert "put_max_bytes(via)" in src
    skill = (
        ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-commands" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "2 MiB" in skill and "5536" in skill
    doc = (ROOT / "airc" / "docs" / "airc-remote-control.md").read_text(encoding="utf-8")
    assert "DCC_BULK_SIZE_CAP" in doc or "2 MiB" in doc
    assert not (
        ROOT / "airc" / "tests" / "test_fr5536_put_dcc_size_cap.py"
    ).read_bytes().startswith(b"\xef\xbb\xbf")
