"""MRB #5601 hostile pins for ou_from_dn parent-container (FR #5587)."""
from __future__ import annotations

import airc_network as nw


def test_mrb5601_trailing_comma_unknown():
    assert nw.ou_from_dn("CN=only,") == "unknown"


def test_mrb5601_space_after_comma():
    assert nw.ou_from_dn("CN=REDQUEEN, CN=Computers,DC=wonderland,DC=local") == (
        "CN=Computers,DC=wonderland,DC=local"
    )


def test_mrb5601_escaped_backslash_then_separator():
    # Even backslash run: comma is a separator. Leaf is CN=foo\
    assert nw.ou_from_dn(r"CN=foo\\,CN=Computers,DC=ex,DC=local") == (
        "CN=Computers,DC=ex,DC=local"
    )
