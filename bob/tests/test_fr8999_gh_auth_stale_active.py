"""FR #8999: stale gh token with Active account true must still block OpenCode.

RedQueen showed ``Failed to log in`` / re-authenticate while hosts.yml still
listed an Active account. ``gh_auth_blocks`` must not treat ``active account``
alone as logged-in when failure cues are present. Never echo status body
(tokens / account names stay out of the block message).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "bob" / "scripts"))

import opencode_seat_contract as c  # noqa: E402


def test_fr8999_stale_active_account_exit0_blocks():
    """Exit 0 + Active account + Failed to log in => block (do not trust Active alone)."""
    stdout = (
        "github.com\n"
        "  X Failed to log in to github.com account EXAMPLE_USER (default)\n"
        "  - Active account: true\n"
        "  - The token in default is invalid.\n"
        "  - To re-authenticate, run: gh auth login -h github.com\n"
    )
    blocked, msg = c.gh_auth_blocks(stdout, "", 0)
    assert blocked is True
    assert "gh_auth_missing" in msg
    assert "gh auth login" in msg
    assert "hosts.yml" in msg
    assert "EXAMPLE_USER" not in msg
    assert "invalid" not in msg.lower() or "invent" in msg.lower()


def test_fr8999_stale_active_account_nonzero_blocks():
    """Non-zero exit with the same stale-token text still blocks."""
    stderr = (
        "Failed to log in to github.com account EXAMPLE_USER (default)\n"
        "Active account: true\n"
        "re-authenticate required\n"
    )
    blocked, msg = c.gh_auth_blocks("", stderr, 1)
    assert blocked is True
    assert msg == c.GH_BLOCK_MESSAGE


def test_fr8999_healthy_logged_in_still_allows():
    blocked, msg = c.gh_auth_blocks(
        "Logged in to github.com account EXAMPLE_USER (keyring)\n"
        "  - Active account: true\n",
        "",
        0,
    )
    assert blocked is False
    assert msg == ""


def test_fr8999_active_account_alone_exit0_without_failure_allows():
    """Active account without failure cues and exit 0 remains allowed."""
    blocked, msg = c.gh_auth_blocks(
        "github.com\n  - Active account: true\n",
        "",
        0,
    )
    assert blocked is False
    assert msg == ""
