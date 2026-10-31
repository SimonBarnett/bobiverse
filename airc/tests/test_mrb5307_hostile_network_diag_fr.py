"""Hostile pins for MRB #5307 (airc NETWORK diag FR vision pack)."""
from __future__ import annotations

from repo_layout import ROOT

FR = ROOT / "airc/docs/feature-request-airc-network-diag-2026-10-31.md"


def test_mrb5307_network_diag_fr_utf8_no_bom_and_locked_bounds():
    raw = FR.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.endswith(b"\n")
    text = raw.decode("utf-8")
    for sid in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"):
        assert f"| {sid} |" in text
    assert "max 500" in text or "**500**" in text
    assert "32" in text
    assert "1s" in text
    assert "reachable = any(ping_ok)" in text
    assert "DCCLISTEN" in text
    assert "same id=" in text or "same job" in text
    assert "dcc-fail" in text
    assert "#5302" in text
    assert "See `drafts/backlog.md`" not in text
    assert "shell=off" in text
    assert "airc/VISION.md" in text
