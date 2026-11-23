"""FR #8806 / BOB-D2: relative Depends-on #N resolves against the FR's own repo."""
from __future__ import annotations

import pytest

from depends_on_parse import resolve_depends_ref


def test_relative_hash_uses_fr_own_repo():
    """S1: #123 with FR repo SimonBarnett/foo -> SimonBarnett/foo#123."""
    assert resolve_depends_ref("SimonBarnett/foo", "#123") == "SimonBarnett/foo#123"


def test_relative_hash_other_repo():
    assert (
        resolve_depends_ref("SimonBarnett/bobiverse", "#8806")
        == "SimonBarnett/bobiverse#8806"
    )


def test_full_owner_repo_hash_unchanged():
    assert (
        resolve_depends_ref("SimonBarnett/foo", "other/bar#9") == "other/bar#9"
    )


def test_full_ref_same_repo_normalized():
    assert (
        resolve_depends_ref("SimonBarnett/foo", "SimonBarnett/foo#7")
        == "SimonBarnett/foo#7"
    )


def test_relative_rejects_wrong_repo_fail_when():
    """fail-when: #123 must not resolve to a different owner/repo."""
    got = resolve_depends_ref("SimonBarnett/foo", "#123")
    assert got != "SimonBarnett/bobiverse#123"
    assert got.startswith("SimonBarnett/foo#")


def test_empty_and_none_raise():
    with pytest.raises(ValueError):
        resolve_depends_ref("SimonBarnett/foo", "")
    with pytest.raises(ValueError):
        resolve_depends_ref("SimonBarnett/foo", "(none)")
    with pytest.raises(ValueError):
        resolve_depends_ref("", "#1")
