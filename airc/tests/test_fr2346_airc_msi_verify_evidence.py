"""FR #2346: ionos airc MSI verify evidence stays present with step matrix."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EV = ROOT / "docs" / "evidence" / "fr2346-ionos-airc-msi-verify-2026-10-04.md"


def test_fr2346_evidence_has_step_matrix():
    assert EV.is_file(), f"missing {EV}"
    text = EV.read_text(encoding="utf-8")
    for needle in (
        "Live service survives",
        "PASS",
        "FAIL",
        "no-matching-asset",
        "airc-0.1.22.msi",
        "#2354",
        "#2355",
        "RunUninstall",
        "Ergo",
    ):
        assert needle in text, f"missing {needle!r}"
