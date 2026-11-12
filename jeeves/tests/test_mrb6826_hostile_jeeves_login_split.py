"""MRB #6826: login bundle split is docs-only; six slices stay open."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "bob" / "docs" / "fr" / "cli-token-compare"
VISION = ROOT / "bob" / "docs" / "vision-cli-token-compare-2026-11-12.md"
TSV = PACK / "SMALL-FRS.tsv"

WANT = {
    "FR-007": 6815,
    "FR-008": 6816,
    "FR-009": 6818,
    "FR-010": 6819,
    "FR-011": 6820,
    "FR-012": 6821,
}


def test_mrb6826_tsv_six_slices_and_closed_bundle():
    raw = TSV.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf"
    text = TSV.read_text(encoding="utf-8")
    rows = {}
    for line in text.splitlines()[1:]:
        parts = line.split("\t")
        rows[parts[0]] = int(parts[1])
    assert rows["FR-006"] == 6798
    for fid, num in WANT.items():
        assert rows[fid] == num
        slug = {
            "FR-007": "jeeves-get-login",
            "FR-008": "butler-graphic",
            "FR-009": "home-link",
            "FR-010": "session-login",
            "FR-011": "session-cookie",
            "FR-012": "appliance-doc",
        }[fid]
        md = PACK / f"{fid}-{slug}.md"
        body = md.read_text(encoding="utf-8")
        assert f"#{num}" in body
        assert "Stays open" in body or "stays open" in body.lower()
        assert "Closes" not in body


def test_mrb6826_fr006_do_not_implement_closed_bundle():
    body = (PACK / "FR-006-bob-ntsa-uk-jeeves-login.md").read_text(encoding="utf-8")
    assert "#6798" in body
    assert "Do not implement this issue" in body
    assert "6815" in body and "6821" in body


def test_mrb6826_vision_s5_bob_ntsa_uk_not_omnibus():
    text = VISION.read_text(encoding="utf-8")
    assert "https://bob.ntsa.uk/jeeves" in text
    assert "#6798 was the login bundle and is closed" in text
    assert "#6815" in text
    assert "bob/docs/fr/cli-token-compare/FR-007-jeeves-get-login.md" in text
    fr = (ROOT / "bob" / "docs" / "feature-request-cli-token-compare-2026-11-12.md").read_text(
        encoding="utf-8"
    )
    assert "Anti-omnibus" in fr
    assert "Implementation issues stay open" in fr
