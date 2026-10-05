"""Hostile MRB #2356: FR #2346 evidence must keep the honest FAIL/SKIP matrix."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EV = ROOT / "docs" / "evidence" / "fr2346-ionos-airc-msi-verify-2026-10-04.md"


def test_evidence_utf8_no_bom():
    raw = EV.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "evidence must be UTF-8 without BOM"
    text = raw.decode("utf-8")
    assert "Ã" not in text and "╬" not in text


def test_evidence_records_fail_and_skip_honestly():
    text = EV.read_text(encoding="utf-8")
    # Live survive is the CAST IRON constraint of the TEST job.
    assert "| 1. Live service survives | **PASS** |" in text
    # Release gap + self-update fail must stay visible (not papered over).
    assert "| 2a. airc MSI on release v0.1.22 | **FAIL** |" in text
    assert "| 2e. Self-update Check | **FAIL** |" in text
    assert "no-matching-asset" in text
    # Live msiexec paths must remain SKIP while production Airc is sacred.
    assert "| 2d. Upgrade over live 0.1.21 | **SKIP** |" in text
    assert "| 2h. Live uninstall cleanliness | **SKIP** |" in text
    # Gap FRs filed instead of silent FAIL.
    assert "#2354" in text and "#2355" in text
    assert "Ergo/BobIrcd untouched" in text or "No Ergo / BobIrcd changes" in text
