"""FR #6150 / FR-010: docs+skills describe ear publish, bob host, OpenCode, Copilot, logos."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob" / "SKILL.md"
EAR = ROOT / "bob" / "docs" / "bob-ear.md"
SPEC = ROOT / "bob" / "docs" / "functional-spec-digest-ear-publish.md"
PARK = ROOT / "bob" / "docs" / "fr" / "digest-ear-publish"
PARK_README = PARK / "README.md"
FR010 = PARK / "FR-010.md"
ISSUED = PARK / "ISSUED.tsv"


def _read(p: Path, *, ascii_only: bool = False) -> str:
    raw = p.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), p
    text = raw.decode("utf-8")
    if ascii_only:
        non = [c for c in text if ord(c) > 127]
        assert not non, f"{p} non-ascii {[hex(ord(c)) for c in non[:5]]}"
    return text


def test_fr6150_skill_ear_publish_bob_host_opencode_copilot_logos():
    text = _read(SKILL)
    assert "https://bob.ntsa.uk/bob/v1/report" in text
    assert "publish_local_peer_fuel" in text
    low = text.lower()
    assert "ear owns" in low or "ear-owned" in low
    assert "opencode-free" in text and "opencode-go" in text
    assert "Copilot" in text or "copilot" in text
    assert "fuel-logos" in text or "Get-BobTrayFuelLogo" in text
    # New FR-010 section must be ASCII (FR #3935)
    start = text.index("## Digest fuel publish")
    rest = text[start + 2 :]
    end_rel = rest.find("\n## ")
    section = text[start : start + 2 + end_rel] if end_rel != -1 else text[start : start + 2000]
    non = [c for c in section if ord(c) > 127]
    assert not non, non[:5]
    for line in section.splitlines():
        assert not line.strip().startswith("Closes "), line


def test_fr6150_bob_ear_docs_digest_fuel_surface():
    text = _read(EAR)
    assert "https://bob.ntsa.uk/bob/v1/report" in text
    assert "publish_local_peer_fuel" in text
    assert "opencode-free" in text and "opencode-go" in text
    assert "Copilot" in text or "copilot" in text
    assert "fuel-logos" in text
    start = text.index("## Digest fuel publish")
    rest = text[start + 2 :]
    end_rel = rest.find("\n## ")
    section = text[start : start + 2 + end_rel] if end_rel != -1 else text[start : start + 1500]
    non = [c for c in section if ord(c) > 127]
    assert not non, non[:5]


def test_fr6150_functional_spec_still_pins_surface():
    text = _read(SPEC, ascii_only=True)
    assert "bob.ntsa.uk" in text
    assert "opencode-free" in text and "opencode-go" in text
    assert "logo" in text.lower()
    assert "Copilot" in text or "copilot" in text


def test_fr6150_park_uses_refs_not_closes_for_impl():
    for path in (PARK_README, FR010, ISSUED):
        text = _read(path, ascii_only=True)
        for line in text.splitlines():
            assert not line.strip().startswith("Closes "), path
    fr = _read(FR010, ascii_only=True)
    assert "Refs" in fr
    assert "SimonBarnett/bobiverse#6141" in fr or "Refs SimonBarnett/bobiverse#" in fr


def test_fr6150_issued_maps_fr010_to_6150():
    rows = _read(ISSUED, ascii_only=True).strip().splitlines()
    mapping = {}
    for line in rows[1:]:
        fr, gh, *_ = line.split("\t")
        mapping[fr] = int(gh)
    assert mapping["FR-010"] == 6150
