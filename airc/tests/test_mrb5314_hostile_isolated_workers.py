"""Hostile pins for MRB #5314 (airc isolated workers in-service CAST IRON)."""
from __future__ import annotations

from repo_layout import ROOT

VISION = ROOT / "airc/VISION.md"
DOC = ROOT / "airc/docs/airc-isolated-workers-in-service.md"


def test_mrb5314_vision_isolated_workers_ascii_no_peer_binaries():
    raw = VISION.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "\u2014" not in text
    assert "in-service deployment only" in text
    assert "no separate product binaries" in text.lower() or "No separate product binaries" in text
    assert "docs/airc-isolated-workers-in-service.md" in text
    locked = text[text.index("## LOCKED") : text.index("## UNKNOWN")]
    assert "isolated workers" in locked


def test_mrb5314_isolated_workers_doc_rule_and_fail_when():
    raw = DOC.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.endswith(b"\n")
    text = raw.decode("utf-8")
    assert "\u2014" not in text
    assert "MUST NOT" in text
    assert "NetworkDiag.exe" in text
    assert "PriorityClient.exe" in text
    assert "LEGION" in text
    assert "#5302" in text
    assert "#5275" in text
