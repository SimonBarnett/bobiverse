"""MRB #5431 hostile pins for FR #5397 per-fuel cooldown docs."""
from __future__ import annotations

from repo_layout import ROOT


def test_mrb5431_docs_and_source_name_per_fuel_keys():
    src = (ROOT / "common" / "scripts" / "copilot_dispatch.py").read_text(encoding="utf-8")
    doc = (ROOT / "jeeves" / "docs" / "webhooks.md").read_text(encoding="utf-8")
    assert "FR #5397" in src
    assert "fuels" in src
    assert "_ = fuel" not in src
    assert "FR #5397" in doc
    assert "fuels.<name>.exhausted_until" in doc
    assert "does not pause Copilot" in doc
    assert not (ROOT / "jeeves" / "docs" / "webhooks.md").read_bytes().startswith(b"\xef\xbb\xbf")
