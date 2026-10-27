"""Hostile MRB #5078 / FR #5069: live DCC-fail capture must stay unique-seq."""
from __future__ import annotations

import re
from pathlib import Path

_SEQ = re.compile(r"^(?:out|err) id=([0-9a-f]{8}) seq=(\d+) ", re.I)
_EVID = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "evidence"
    / "fr-5069-dcc-fallback-live-retest"
)


def test_mrb5078_live_replies_unique_seq_and_fallback():
    lines = (_EVID / "retest-replies.txt").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 51
    seqs = [int(m.group(2)) for ln in lines if (m := _SEQ.match(ln))]
    assert seqs == list(range(1, 51))
    assert len(seqs) == len(set(seqs))
    assert lines[-1] == "DONE id=b6782a52 exit=0"
    assert "falling back to IRC" in lines[-2]
    assert "seq=50" in lines[-2]
    assert not any("via=dcc" in ln for ln in lines)
    assert "seq=1" not in lines[-2]


def test_mrb5078_parse_summary_matches_replies():
    summary = (_EVID / "retest-parse-summary.txt").read_text(encoding="utf-8")
    assert "seq_unique=50" in summary
    assert "parse=PASS" in summary
    assert "exit=0" in summary
    assert "seq=50 dcc failed" in summary
    assert "91648f9b" in summary
