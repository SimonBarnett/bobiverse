"""docs/mrb-7061: hostile pin for fleet-ops 2470 non-allowlist ALERT lesson."""
from __future__ import annotations
from repo_layout import REPO
SKILL = REPO / "common" / ".grok" / "skills" / "bobiverse-fleet-ops" / "SKILL.md"

def test_docs_mrb_7061_2470_non_allowlist_alert_lesson():
    text = SKILL.read_text(encoding="utf-8")
    needle = (
        "A 2470 behind-count ALERT test must dirty a non-allowlist path; "
        "park-all-dirty makes ff succeed and drops the ALERT."
    )
    assert needle in text
