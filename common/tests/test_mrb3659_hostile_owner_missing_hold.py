"""docs/mrb-3659: pin FR #3658 hold title SKIP_FR + ensure_labels needles on main."""
from __future__ import annotations
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
def test_mrb3659_gitclaim_hold_title_regex():
    t = (ROOT / "common/scripts/gitclaim.py").read_text(encoding="utf-8")
    assert "HARVEST_OWNER_MISSING_HOLD_TITLE_RE" in t
    assert "owner_missing_hold_title" in t
    assert r"^harvest:\s*hold\s+for\b" in t or "harvest:\\s*hold\\s+for\\b" in t
def test_mrb3659_gh_filer_ensure_labels():
    t = (ROOT / "common/scripts/gh_filer.py").read_text(encoding="utf-8")
    assert "def ensure_labels" in t
    assert "owner-missing" in t or "FR #3658" in t