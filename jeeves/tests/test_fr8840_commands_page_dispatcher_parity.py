"""FR #8840: /jeeves/commands page + docs + skill match chair_commands.COMMANDS."""
from __future__ import annotations

import re
from pathlib import Path

import chair_commands as cc
from repo_layout import REPO

WWW_PAGE = REPO / "jeeves" / "www" / "irc-ntsa" / "jeeves" / "commands" / "index.html"
DOCS_MD = REPO / "jeeves" / "docs" / "jeeves-commands.md"
SKILL_MD = REPO / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-commands" / "SKILL.md"

# Documented on the public page but not chair PM COMMANDS (ear / shop wire).
PAGE_EXTRAS = frozenset(
    {
        "startworker",  # Bob ear (t810u), not Jeeves chair
        "bored",  # shop wire
        "ack",
        "done",
        "nack",
        "giveup",
    }
)

# Lowercase bang verbs only (skip HTML !DOCTYPE).
_BANG_NAME = re.compile(r"!([a-z][a-z0-9_]*)")
# Bare ping (no bang) as its own token in code/table cells.
_PING = re.compile(r"(?<![A-Za-z0-9_])ping(?![A-Za-z0-9_])", re.I)


def _dispatcher_names() -> set[str]:
    return {c.name.lower() for c in cc.COMMANDS}


def _names_in_text(text: str) -> set[str]:
    found = {m.group(1).lower() for m in _BANG_NAME.finditer(text)}
    if _PING.search(text):
        found.add("ping")
    return found


def test_fr8840_dispatcher_registry_valid():
    assert not cc.validate_registry()
    assert "build" in _dispatcher_names()
    assert "stuck" in _dispatcher_names()


def test_fr8840_page_lists_every_dispatcher_command():
    text = WWW_PAGE.read_text(encoding="utf-8")
    present = _names_in_text(text)
    missing = sorted(_dispatcher_names() - present)
    assert not missing, f"commands page missing dispatcher commands: {missing}"


def test_fr8840_page_has_no_unknown_commands():
    text = WWW_PAGE.read_text(encoding="utf-8")
    present = _names_in_text(text)
    unknown = sorted(present - _dispatcher_names() - PAGE_EXTRAS)
    assert not unknown, f"commands page lists unknown commands: {unknown}"


def test_fr8840_docs_list_every_dispatcher_command():
    text = DOCS_MD.read_text(encoding="utf-8")
    present = _names_in_text(text)
    missing = sorted(_dispatcher_names() - present)
    assert not missing, f"jeeves-commands.md missing dispatcher commands: {missing}"


def test_fr8840_skill_lists_every_dispatcher_command():
    text = SKILL_MD.read_text(encoding="utf-8")
    present = _names_in_text(text)
    missing = sorted(_dispatcher_names() - present)
    assert not missing, f"bobiverse-jeeves-commands SKILL.md missing: {missing}"


def test_fr8840_removing_build_from_page_fixture_fails(tmp_path: Path, monkeypatch):
    """Acceptance: taking !build out of the page makes the test name !build."""
    raw = WWW_PAGE.read_text(encoding="utf-8")
    stripped = raw.replace("!build", "!bld_removed")
    fake = tmp_path / "index.html"
    fake.write_text(stripped, encoding="utf-8")
    present = _names_in_text(fake.read_text(encoding="utf-8"))
    missing = sorted(_dispatcher_names() - present)
    assert "build" in missing


def test_fr8840_fake_zzz_on_page_fixture_fails(tmp_path: Path):
    """Acceptance: a fake !zzz on the page (no handler) is named as unknown."""
    raw = WWW_PAGE.read_text(encoding="utf-8")
    spiked = raw.replace(
        "</tbody>",
        "<tr><td><code>!zzz</code></td><td>anyone</td><td>fake</td></tr>\n      </tbody>",
        1,
    )
    fake = tmp_path / "index.html"
    fake.write_text(spiked, encoding="utf-8")
    present = _names_in_text(fake.read_text(encoding="utf-8"))
    unknown = sorted(present - _dispatcher_names() - PAGE_EXTRAS)
    assert "zzz" in unknown
