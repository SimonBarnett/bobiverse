"""docs/mrb-4815 hostile pins for FR #4795 / PR #4815 GETCHUNK pull-mode fetch."""
from __future__ import annotations

from pathlib import Path

import airc_jobs as jobs


def test_mrb4815_getchunk_registered_as_read_verb():
    assert jobs.VERB_LEVELS.get("GETCHUNK") == "read"
    parsed = jobs.parse_job_verb("GETCHUNK id=aabbccdd seq=1")
    assert parsed is not None
    verb, kv = parsed
    assert verb == "GETCHUNK"
    assert kv["id"] == "aabbccdd"
    assert kv["seq"] == "1"


def test_mrb4815_open_fetch_has_no_data_payload(tmp_path: Path):
    store = jobs.JobStore(tmp_path / "home")
    (store.drop_root / "big.bin").write_bytes(b"Z" * 500)
    proto = jobs.JobProtocol(store)
    lines = proto.handle("op", "GET", {"path": "big.bin", "fetch": "chunk"})
    assert len(lines) == 1
    assert "data=" not in lines[0]
    assert "seqs=" in lines[0]


def test_mrb4815_skill_and_docs_cite_getchunk():
    root = Path(__file__).resolve().parents[1]
    skill = (root / ".grok" / "skills" / "bobiverse-airc-troubleshooting" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    docs = (root / "docs" / "airc-remote-control.md").read_text(encoding="utf-8")
    assert "FR #4795" in skill
    assert "GETCHUNK" in skill
    assert "fetch=chunk" in docs
    assert "GETCHUNK" in docs
