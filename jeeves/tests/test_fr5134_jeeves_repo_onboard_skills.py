"""FR #5134: Jeeves skills cover repo onboarding (MRB filter) and give-up clear / re-assign."""
from __future__ import annotations

from pathlib import Path

import chair_commands
import chair_health as ch
from repo_layout import ROOT

REPOS_SKILL = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-repos/SKILL.md"
COMMANDS = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-commands/SKILL.md"
TROUBLE = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-troubleshooting/SKILL.md"
DOCS = ROOT / "jeeves/docs/jeeves-commands.md"
PACK = ROOT / "jeeves/defaults/resync-repos.txt"


def _utf8(p: Path) -> str:
    raw = p.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM in {p}"
    return raw.decode("utf-8")


def test_fr5134_help_lists_focus_and_resync():
    names = {c.name for c in chair_commands.COMMANDS}
    assert "focus" in names
    assert "resync" in names
    assert "help" in names


def test_fr5134_default_resync_includes_priority_branding():
    assert "SimonBarnett/priority-branding" in ch.DEFAULT_RESYNC_REPOS
    text = _utf8(PACK if PACK.is_file() else ROOT / "defaults/resync-repos.txt")
    assert "SimonBarnett/priority-branding" in text


def test_fr5134_repos_skill_onboard_and_giveup_playbooks():
    t = _utf8(REPOS_SKILL)
    assert "name: bobiverse-jeeves-repos" in t
    assert "FR #5134" in t
    # Which file discovery actually reads
    assert ".jeeves" in t and "resync-repos.txt" in t
    assert "configured_repos" in t or "chair --home" in t or "BOB_HOME" in t
    assert "JEEVES_RESYNC_REPOS" in t
    # Twin / digest home called out so ops do not edit the wrong copy alone
    assert ".bobiverse" in t
    assert "focus.json" in t
    assert "!focus" in t and "!resync" in t
    assert "resync: roster refresh requested; GitHub FR/MRB re-sync queued" in t
    assert "priority=9 (low)" in t or "priority=9" in t
    assert "SimonBarnett/priority-branding" in t
    # Give-up recovery
    assert "GIVEUP_COOLDOWN_S" in t
    assert "600" in t
    assert "queue.json" in t
    assert "giveup_seats" in t
    assert "cooldown_until" in t
    assert "seat-ledger.json" in t
    assert "!assign" in t
    assert "!resync" in t and "does not clear" in t.lower()
    # Follow-up gap (document only; no command yet)
    assert "!cleargiveup" in t
    # Webhook note
    assert "webhook" in t.lower()
    # Never restart during !build
    assert "!build" in t


def test_fr5134_commands_and_troubleshooting_cross_link():
    cmd = _utf8(COMMANDS)
    assert "bobiverse-jeeves-repos" in cmd
    assert "FR #5134" in cmd
    tr = _utf8(TROUBLE)
    assert "bobiverse-jeeves-repos" in tr or "resync-repos.txt" in tr
    assert "seat-ledger.json" in tr
    docs = _utf8(DOCS)
    assert "FR #5134" in docs
    assert "resync-repos.txt" in docs
    assert "bobiverse-jeeves-repos" in docs or "Onboard a repo" in docs
