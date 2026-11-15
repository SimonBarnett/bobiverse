"""FR #7586: ear provenance fr= must list FRs whose code is in the artifact.

build-bob-ear.yml hardcodes provenance ``fr=...``. When shipped runtime sources
carry an FR marker (e.g. bobreport.py FR #7549), that number must appear in the
list so Slab/install digests match the build contents.
"""
from __future__ import annotations

import re
from pathlib import Path

from repo_layout import ROOT

WF = ROOT / ".github" / "workflows" / "build-bob-ear.yml"
BOBREPORT = ROOT / "common" / "scripts" / "bobreport.py"
OPENCODE_FUEL = ROOT / "common" / "scripts" / "opencode_fuel.py"
IRC_AGENT = ROOT / "common" / "scripts" / "irc_agent.py"

# Runtime files copied into the ear artifact (or frozen into bob-ear.exe).
ARTIFACT_SOURCES = (BOBREPORT, OPENCODE_FUEL, IRC_AGENT)

# FR markers that must be declared in provenance when present in artifact sources.
# Keep this list to FRs that landed in ear runtime and are tracked on the fr= line.
REQUIRED_WHEN_PRESENT = (
    7179,
    7390,
    7394,
    7548,
    7549,
)


def _provenance_fr_ids(text: str | None = None) -> set[int]:
    blob = text if text is not None else WF.read_text(encoding="utf-8")
    m = re.search(r'"fr=([0-9,]+)"', blob)
    assert m, "build-bob-ear.yml missing provenance fr= line"
    return {int(x) for x in m.group(1).split(",") if x.strip()}


def _artifact_source_text() -> str:
    parts: list[str] = []
    for path in ARTIFACT_SOURCES:
        assert path.is_file(), path
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_fr7586_7549_in_bobreport_and_provenance():
    """Acceptance: build with #7549 code lists 7549 in provenance fr=."""
    report = BOBREPORT.read_text(encoding="utf-8")
    assert "FR #7549" in report
    assert 7549 in _provenance_fr_ids()


def test_fr7586_provenance_lists_frs_present_in_artifact_sources():
    """Gate: omit from fr= only when the marker is also gone from artifact sources."""
    sources = _artifact_source_text()
    fr_ids = _provenance_fr_ids()
    missing: list[int] = []
    for num in REQUIRED_WHEN_PRESENT:
        if re.search(rf"FR\s*#{num}\b", sources) and num not in fr_ids:
            missing.append(num)
    assert missing == [], f"provenance fr= omits FRs present in ear artifact sources: {missing}"


def test_fr7586_workflow_fr_line_is_sorted_unique_csv():
    text = WF.read_text(encoding="utf-8")
    m = re.search(r'"fr=([0-9,]+)"', text)
    assert m
    nums = [int(x) for x in m.group(1).split(",") if x.strip()]
    assert nums == sorted(set(nums)), "fr= must be unique ascending ids"
    assert "7549" in m.group(1)
