# -*- coding: utf-8 -*-
"""FR #9906: never set GIT_ASKPASS to echo GH_TOKEN / GITHUB_TOKEN.

Fail-when: skills or scripts teach AskPass that prints the token into the
terminal transcript (operator harvest-MRB fold leak class).
"""
from __future__ import annotations

import re
from pathlib import Path

from repo_layout import REPO

HARVEST = REPO / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"
MRB = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
FLEET = REPO / "common" / ".grok" / "skills" / "bobiverse-fleet-ops" / "SKILL.md"

# Bad patterns that materialize the token when AskPass runs (or teach that).
ASKPASS_ECHO_RX = re.compile(
    r"(?is)GIT_ASKPASS.{0,120}(?:echo|Write-Output|Write-Host).{0,80}"
    r"(?:GH_TOKEN|GITHUB_TOKEN|gh\s+auth\s+token)"
)
# Explicit anti-pattern teaching (must appear in skills).
FORBID_MARKERS = (
    "Never set GIT_ASKPASS",
    "FR #9906",
)


def _utf8(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM in {path}"
    return raw.decode("utf-8")


def test_fr9906_skills_forbid_git_askpass_echo_token():
    for path in (HARVEST, MRB, FLEET):
        assert path.is_file(), path
        text = _utf8(path)
        assert "FR #9906" in text, path
        assert "Never set GIT_ASKPASS" in text or "never set GIT_ASKPASS" in text.lower(), path
        assert "GH_TOKEN" in text or "GITHUB_TOKEN" in text
        # Prefer env / gh helper wording.
        assert (
            "credential helper" in text.lower()
            or "GH_TOKEN env" in text
            or "gh auth" in text.lower()
        ), path


def test_fr9906_repo_scripts_do_not_assign_askpass_echo():
    """Tracked .ps1/.py must not wire AskPass to echo the token."""
    roots = (
        REPO / "common" / "scripts",
        REPO / "bob" / "scripts",
        REPO / "jeeves" / "scripts",
    )
    hits: list[str] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() not in {".ps1", ".py", ".md"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if ASKPASS_ECHO_RX.search(text):
                # Allow the forbid docs themselves to mention the anti-pattern.
                if path in (HARVEST, MRB, FLEET) or path.name.startswith("test_fr9906"):
                    continue
                if "Never set GIT_ASKPASS" in text and "FR #9906" in text:
                    continue
                hits.append(str(path.relative_to(REPO)))
    assert hits == [], f"GIT_ASKPASS echo token pattern in: {hits}"
