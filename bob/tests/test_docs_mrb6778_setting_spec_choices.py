"""docs/mrb-6778: SettingSpec.choices playbook contiguous in bobiverse-bob."""
from __future__ import annotations

from pathlib import Path

SKILL = Path(__file__).resolve().parents[2] / "bob" / ".grok" / "skills" / "bobiverse-bob" / "SKILL.md"


def test_docs_mrb6778_setting_spec_choices_contiguous():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    needle = (
        "Non-empty SettingSpec.choices on a non-bool setting render a select; "
        "a value outside the list is an extra selected option; bools stay checkboxes; "
        "do not invent SCHEMA choices for paths URLs or seconds."
    )
    assert needle in text
    idx = text.index(needle)
    window = text[max(0, idx - 80) : idx + len(needle) + 80]
    assert "Do not park this playbook under harvest/SKILL.md" in window
    assert "TipForm:" in window
