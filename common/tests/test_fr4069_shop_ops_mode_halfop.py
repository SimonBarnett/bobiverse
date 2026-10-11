"""FR #4069: bob ear shop-op MODE verb allows +h (half-op), not only +o/+v."""
from __future__ import annotations

import pytest

import shop_ops


def test_mode_re_allows_op_voice_halfop():
    for mode in ("+o", "-o", "+v", "-v", "+h", "-h"):
        m = shop_ops.MODE_RE.match(f"MODE #marchhare {mode} slab-hop")
        assert m is not None, mode
        assert m.group("mode") == mode
        assert m.group("chan") == "#marchhare"
        assert m.group("nick") == "slab-hop"


@pytest.mark.parametrize(
    "bad",
    [
        "MODE #marchhare +a slab",
        "MODE #marchhare +q slab",
        "MODE #marchhare +b slab",
        "MODE #marchhare +oh slab",
        "MODE #marchhare +H slab",
        "MODE #marchhare o slab",
        "MODE #marchhare +h",
    ],
)
def test_mode_re_rejects_other_modes(bad: str):
    assert shop_ops.MODE_RE.match(bad) is None


def test_raw_op_line_allows_halfop_on_own_shop():
    assert (
        shop_ops.raw_op_line("MODE #marchhare +h slab-hop", "bob-marchhare")
        == "MODE #marchhare +h slab-hop"
    )
    assert (
        shop_ops.raw_op_line("MODE #marchhare -h slab-hop", "Bob-marchhare")
        == "MODE #marchhare -h slab-hop"
    )


def test_raw_op_line_still_allows_op_and_voice():
    assert shop_ops.raw_op_line("MODE #marchhare +o slab", "bob-marchhare") == "MODE #marchhare +o slab"
    assert shop_ops.raw_op_line("MODE #marchhare +v slab", "bob-marchhare") == "MODE #marchhare +v slab"


def test_raw_op_line_rejects_halfop_on_foreign_channel():
    assert shop_ops.raw_op_line("MODE #bobiverse +h slab", "bob-marchhare") is None
    assert shop_ops.raw_op_line("MODE #other +h slab", "bob-marchhare") is None


def test_raw_op_line_rejects_unsupported_mode_letters():
    assert shop_ops.raw_op_line("MODE #marchhare +a slab", "bob-marchhare") is None
    assert shop_ops.raw_op_line("MODE #marchhare +q slab", "bob-marchhare") is None
