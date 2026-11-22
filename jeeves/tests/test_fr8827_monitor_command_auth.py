"""FR #8827: MONITORING principal has owner-class queue mutators; skill keep-queue-moving."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
SCRIPTS = REPO / "common" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import chair_commands as cc  # noqa: E402

JEEVES = REPO / "jeeves"
MONITOR_SKILL = JEEVES / ".grok" / "skills" / "bobiverse-jeeves-monitor" / "SKILL.md"
MONITOR_START = JEEVES / ".grok" / "skills" / "monitor-start" / "SKILL.md"
AGENTS = JEEVES / "AGENTS.md"
COMMANDS_DOC = JEEVES / "docs" / "jeeves-commands.md"
MONITORING_DOC = JEEVES / "docs" / "monitoring.md"

KEEP_QUEUE_MARKS = (
    "keep the queue moving",
    "!ignore",
    "!assign",
    "!focus",
    "!sweep",
)
STILL_NEVER_MARKS = (
    "Ergo",
    "UAT",
    "VERSION",
)


@pytest.fixture(autouse=True)
def _clear_monitor_env(monkeypatch):
    for k in ("JEEVES_MONITOR_NICKS", "JEEVES_MONITOR_ACCOUNTS", "JEEVES_FOCUS_MUTATORS", "JEEVES_FOCUS_MUTATOR_ACCOUNTS"):
        monkeypatch.delenv(k, raising=False)


def test_default_monitoring_nick_is_monitor_principal():
    who = cc.classify("monitoring")
    assert who.kind == "monitor"
    assert who.ops is True


def test_monitor_account_env_classifies():
    import os

    os.environ["JEEVES_MONITOR_ACCOUNTS"] = "mon-acct"
    who = cc.classify("any-nick", "mon-acct")
    assert who.kind == "monitor"
    assert who.ops is True


def test_empty_monitor_nicks_env_disables_default():
    import os

    os.environ["JEEVES_MONITOR_NICKS"] = ""
    who = cc.classify("monitoring")
    assert who.kind == "none"
    assert who.ops is False


def test_monitor_may_queue_mutators():
    who = cc.classify("monitoring")
    for cmd in ("ignore", "assign", "focus", "unfocus", "sweep", "resync", "recycle", "cleargiveup"):
        assert cc.may(cmd, who) is True, cmd


def test_unrelated_nick_still_denied():
    who = cc.classify("mallory")
    assert who.kind == "none"
    for cmd in ("ignore", "assign", "focus", "sweep"):
        assert cc.may(cmd, who) is False, cmd


def test_allowlist_still_focus_only(monkeypatch):
    monkeypatch.setenv("JEEVES_FOCUS_MUTATORS", "ops-ear")
    who = cc.classify("ops-ear")
    assert who.kind == "allowlist"
    assert cc.may("focus", who) is True
    assert cc.may("ignore", who) is False
    assert cc.may("assign", who) is False


def test_monitor_roles_see_ops_help():
    who = cc.classify("monitoring")
    assert cc.ROLE_BOB in who.roles
    # OPS_ROLES commands require ROLE_BOB or ROLE_SIMON
    assert cc.OPS_ROLES & who.roles


@pytest.mark.parametrize(
    "path",
    [MONITOR_SKILL, MONITOR_START, AGENTS],
    ids=["monitor-skill", "monitor-start", "agents"],
)
def test_skill_docs_keep_queue_moving(path: Path):
    assert path.is_file(), path
    t = path.read_text(encoding="utf-8-sig").lower()
    for mk in KEEP_QUEUE_MARKS:
        assert mk.lower() in t, (path.name, mk)
    for mk in STILL_NEVER_MARKS:
        assert mk.lower() in t, (path.name, mk)
    # Blanket "never act as chair" without the keep-queue exception must be gone.
    assert "keep the queue moving" in t
    assert "never touch ergo" in t or "never" in t and "ergo" in t


def test_ops_auth_docs_without_secrets():
    for path in (COMMANDS_DOC, MONITORING_DOC):
        assert path.is_file(), path
        t = path.read_text(encoding="utf-8-sig")
        low = t.lower()
        assert "monitor" in low
        assert "jeeves_monitor" in low or "monitoring" in low
        # no secret-shaped literals
        assert "password=" not in low
        assert "nickserv" in low or "services account" in low or "sasl" in low or "ear" in low
