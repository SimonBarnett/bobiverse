"""FR #9882: chair offers on worker ready (+ DONE); !bored is fallback only."""
from __future__ import annotations

import sys
from pathlib import Path

from repo_layout import REPO

SCRIPTS = REPO / "common" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import gitclaim  # noqa: E402


def test_is_worker_ready_line_matches_shop_forms():
    assert gitclaim.is_worker_ready_line("worker ready") is True
    assert gitclaim.is_worker_ready_line("Worker Ready") is True
    assert gitclaim.is_worker_ready_line("redqueen-5792 worker ready") is True
    assert gitclaim.is_worker_ready_line("  flamingo-99 worker ready  ") is True
    assert gitclaim.is_worker_ready_line("!bored") is False
    assert gitclaim.is_worker_ready_line("DONE FR SimonBarnett/bobiverse#1") is False
    assert gitclaim.is_worker_ready_line("ready for work") is False
    assert gitclaim.is_worker_ready_line("") is False


def test_cast_iron_docs_name_bored_as_fallback():
    docs = (REPO / "jeeves" / "docs" / "empty-offer-operator.md").read_text(encoding="utf-8")
    assert "FR #9882" in docs
    assert "fallback" in docs.lower()
    assert "worker ready" in docs.lower()
    mon = (REPO / "jeeves" / "docs" / "monitoring.md").read_text(encoding="utf-8")
    assert "FR #9882" in mon


def test_irc_agent_wires_worker_ready_before_bored_fallback():
    irc = (SCRIPTS / "irc_agent.py").read_text(encoding="utf-8")
    assert "is_worker_ready_line" in irc
    assert "FR #9882" in irc
    # Primary path must appear before the !bored branch in _maybe_git_claim.
    ready_at = irc.find("is_worker_ready_line")
    bored_at = irc.find("is_bored_command(body)")
    assert ready_at > 0 and bored_at > 0
    assert ready_at < bored_at
