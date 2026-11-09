"""MRB #6244 / FR #6301: known OpenCode Status bars use bar RGB (green->red remaining)."""
from __future__ import annotations

from pathlib import Path

CS = Path(__file__).resolve().parents[1] / "tray" / "dialogs" / "BobStatus.cs"


def test_opencode_bar_rows_set_parse_row_default_rgb():
    src = CS.read_text(encoding="utf-8")
    start = src.find("foreach (OpencodeBarRow b in OpencodePaint.Rows")
    assert start >= 0
    chunk = src[start : start + 700]
    assert "r.Bar.R = b.R" in chunk
    assert "r.Bar.G = b.G" in chunk
    assert "r.Bar.B = b.B" in chunk
    assert "r.Bar.Known = b.Known" in chunk
