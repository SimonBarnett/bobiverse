"""MRB #6181 hostile pins for FR-010 digest docs/skills."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob" / "SKILL.md"
LICENSE = ROOT / "bob" / "tray" / "assets" / "fuel-logos" / "LICENSE.md"


def test_mrb6181_skill_digest_section_ascii_and_refs_only():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    start = text.index("## Digest fuel publish")
    rest = text[start + 2 :]
    end_rel = rest.find("\n## ")
    section = text[start : start + 2 + end_rel] if end_rel != -1 else text[start:]
    assert all(ord(c) < 128 for c in section)
    assert "https://bob.ntsa.uk/bob/v1/report" in section
    assert "opencode-free" in section and "opencode-go" in section
    assert "Closes SimonBarnett/bobiverse#614" not in section
    assert "when a merge payload includes" in section or "build_peer_fuel_merge_payload" in section


def test_mrb6181_fuel_logos_license_on_tree():
    assert LICENSE.is_file(), "FR #6149 LICENSE.md must exist on main tip"
    assert b"\xef\xbb\xbf" not in LICENSE.read_bytes()[:3]
