# -*- coding: utf-8 -*-
"""FR #8805 / BOB-D1: parse Depends-on from issue body (S1 only)."""
from __future__ import annotations

import pytest

from depends_on import parse_depends_on


@pytest.mark.parametrize(
    "body,repo,expected",
    [
        ("Depends-on: #123", "", (("", 123),)),
        ("Depends-on: #123", "o/r", (("o/r", 123),)),
        ("Depends-on: owner/repo#9", "", (("owner/repo", 9),)),
        (
            "Depends-on: #1, owner/other#2 #3",
            "home/repo",
            (("home/repo", 1), ("owner/other", 2), ("home/repo", 3)),
        ),
        ("**Depends-on:** (none)", "", ()),
        (None, "", ()),
        ("", "", ()),
        (
            "# Title\n\n**Depends-on:** #42\n\nMore text\n",
            "SimonBarnett/bobiverse",
            (("SimonBarnett/bobiverse", 42),),
        ),
        ("Depends-on: #7 #7 owner/r#7", "a/b", (("a/b", 7), ("owner/r", 7))),
        ("This depends on #5 in prose", "", ()),
        ("Refs #5\nCloses #5", "", ()),
        (
            "Depends-on: BOB-06, #10, VIS-08, owner/x#11",
            "o/r",
            (("o/r", 10), ("owner/x", 11)),
        ),
        ("depends-on: #8", "o/r", (("o/r", 8),)),
        ("`Depends-on:` #9", "o/r", (("o/r", 9),)),
        ("Depends-on: #0123", "", (("", 123),)),
    ],
)
def test_parse_depends_on(body, repo, expected):
    assert parse_depends_on(body, repo=repo) == expected