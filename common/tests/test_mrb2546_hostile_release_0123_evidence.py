"""MRB #2546 hostile gates for v0.1.23 bob+airc pack evidence (FR #2447/#2511)."""
from __future__ import annotations

from pathlib import Path

import repo_layout

EVIDENCE = repo_layout.REPO / "docs" / "release-0.1.23-pack-evidence.md"
HARVEST = repo_layout.REPO / "common" / "docs" / "skill-harvest-log.md"

# Published airc MSI digest from GH release v0.1.23 (MRB verified 2026-10-05).
AIRC_SHA256 = "7f0786102935ec48f4b759ccab74fcbf4badeb35e41cab587da0a47ada73e2ad"
BOB_SHA256 = "c2367a6f30e0d825399eff508137d042d9a2a0e068e0c1218f78fe1a0fb34ae6"


def test_mrb2546_evidence_doc_gates():
    assert EVIDENCE.is_file()
    raw = EVIDENCE.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "evidence must be UTF-8 no BOM"
    text = raw.decode("utf-8")
    assert "FR #2447" in text and "#2511" in text
    assert "Assert-BobiverseReleaseAssets" in text or "Assert-BobiverseReleaseAssets.ps1" in text
    assert "HomePath" in text
    assert "v0.1.23" in text
    assert AIRC_SHA256 in text
    assert BOB_SHA256 in text
    assert "apply-ok" in text or "Apply" in text
    assert "ionos" in text.lower() or "win-mpre" in text.lower()


def test_mrb2546_harvest_log_repack_lesson():
    text = HARVEST.read_text(encoding="utf-8")
    assert "FR #2447" in text and "#2511" in text
    assert "HomePath" in text or "re-pack" in text.lower()
    assert "Assert-BobiverseReleaseAssets" in text or "Assert" in text
