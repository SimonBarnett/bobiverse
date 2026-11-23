"""FR #8812 (BOB-D8): jeeves-commands documents Depends-on vs hold (enforced).

Hostile MRB #9326 FAIL: tip claimed Depends-on was planned/not enforced after
BOB-D1–D7 landed. This pin requires grammar + hold distinction and live gate.
"""
from __future__ import annotations

from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs" / "jeeves-commands.md"

MARKER = "**Depends-on (enforced) vs hold**"


def _subsection() -> str:
    text = DOCS.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if MARKER in ln:
            start = i
            break
    assert start is not None, "Depends-on vs hold subsection missing"
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].lstrip().startswith("* **"):
            end = j
            break
    return "\n".join(lines[start:end])


def test_fr8812_subsection_documents_depends_on_grammar():
    sub = _subsection()
    assert "Depends-on: #N" in sub
    assert "Depends-on: owner/repo#N" in sub
    assert "Depends-on: (none)" in sub


def test_fr8812_subsection_documents_live_gate_and_reasons():
    sub = _subsection()
    assert "depends-open" in sub
    assert "depends-unresolved" in sub
    assert "BOB-D1" in sub
    assert "#8805" in sub and "#8811" in sub
    assert "row_depends_open_reason" in sub or "row_fr_depends_blocked_reason" in sub


def test_fr8812_subsection_documents_hold_mechanism():
    sub = _subsection()
    assert "`hold`" in sub
    assert "on-hold" in sub or "hold" in sub.lower()
    assert "never" in sub.lower() and "clears a hold" in sub.lower()


def test_fr8812_subsection_claims_depends_gate_enforced_today():
    sub = _subsection()
    assert "yes (BOB-D1" in sub or "enforced" in sub.lower()
    low = sub.lower()
    assert "no (planned)" not in low
    assert "does **not** parse or enforce today" not in sub
    assert "does not parse or enforce today" not in low
