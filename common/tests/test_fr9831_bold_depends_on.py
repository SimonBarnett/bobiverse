# -*- coding: utf-8 -*-
"""FR #9831: Depends-on with optional markdown bold/italics parses for chair gates."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "jeeves" / "tools" / "monitor"))
sys.path.insert(0, str(ROOT / "common" / "scripts"))  # common wins for depends_on

from depends_on import format_depends_on_line, parse_depends_on  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


REPO = "SimonBarnett/bobiverse"
BOLD_CASES = [
    "Depends-on: #9830\n",
    "**Depends-on: #9830**\n",
    "*Depends-on: #9830*\n",
    "**Depends-on:** #9830\n",
    "Depends-on: **#9830**\n",
    "`Depends-on:` #9830\n",
]


def test_fr9831_common_parse_bold_italic_plain():
    for body in BOLD_CASES:
        assert parse_depends_on(body, repo=REPO) == ((REPO, 9830),), body


def test_fr9831_fr_digest_parse_bold_held_digest_stamp():
    """Held-digest monitor must see bold Depends-on (fail-when ignored)."""
    fd = _load("fr_digest_fr9831", ROOT / "jeeves" / "tools" / "monitor" / "fr_digest.py")
    for body in BOLD_CASES:
        assert fd.parse_depends(body, REPO) == [(REPO, 9830)], body


def test_fr9831_monitor_depends_on_parse_bold():
    mon = _load("mon_depends_fr9831", ROOT / "jeeves" / "tools" / "monitor" / "depends_on.py")
    for body in BOLD_CASES:
        assert mon.parse_depends(body, REPO) == [(REPO, 9830)], body


def test_fr9831_format_depends_on_line_is_plain():
    line = format_depends_on_line([(REPO, 9830)], repo=REPO)
    assert line == "Depends-on: #9830"
    assert "*" not in line


def test_fr9831_filing_skill_prefers_plain_depends_on():
    """Filing skills document plain Depends-on: #N (not bold)."""
    paths = [
        ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md",
        ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md",
        ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-agent-monitor" / "SKILL.md",
    ]
    hits = 0
    for p in paths:
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        if "FR #9831" in text or "prefer plain `Depends-on:" in text or "prefer plain Depends-on" in text:
            hits += 1
    assert hits >= 1, "expected at least one filing skill pin for plain Depends-on (FR #9831)"