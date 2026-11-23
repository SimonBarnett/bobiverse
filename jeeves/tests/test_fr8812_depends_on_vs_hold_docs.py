"""FR #8812 (BOB-D8): jeeves-commands documents ``Depends-on`` vs ``hold``.

The Queue hygiene section must distinguish the planned ``Depends-on``
prerequisite gate from the enforced ``hold`` stop, and must not describe the
planned gate as live. Regression pin modelled on ``test_mrb4190_docs_out_of_fuel``
(UTF-8 read, assertions limited to the subsection) with a negative check in the
spirit of ``test_mrb6381``.
"""
from __future__ import annotations

from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs" / "jeeves-commands.md"

MARKER = "**Depends-on (planned) vs hold**"


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


def test_fr8812_subsection_documents_planned_gate_and_reasons():
    sub = _subsection()
    assert "depends-open" in sub
    assert "depends-unresolved" in sub
    assert "planned (BOB-D1" in sub
    assert "#8805" in sub and "#8811" in sub


def test_fr8812_subsection_documents_hold_mechanism():
    sub = _subsection()
    assert "`hold`" in sub
    assert "on-hold" in sub
    assert "`HOLD:`" in sub
    assert "`**HOLD (\u2026):**`" in sub
    assert "never clears a hold" in sub


def test_fr8812_subsection_does_not_claim_depends_gate_enforced_today():
    sub = _subsection()
    for line in sub.splitlines():
        low = line.lower()
        assert not ("depends-on" in low and "enforced today" in low), line
    assert "no (planned)" in sub
