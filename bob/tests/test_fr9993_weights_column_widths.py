"""FR #9993: Model column is twice as wide; Context and Effort are half."""
from repo_layout import ROOT

SRC = (ROOT / "bob" / "tray" / "dialogs" / "WeightsForm.cs").read_text(encoding="utf-8")


def test_fr9993_fill_weights():
    assert "colModel.FillWeight = 200f" in SRC
    assert "colContext.FillWeight = 50f" in SRC
    assert "colEffort.FillWeight = 50f" in SRC
    assert SRC.index("colModel.FillWeight") < SRC.index("colContext.FillWeight")
