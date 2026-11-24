"""FR #9049: Invoke-JeevesMonitorCheck ValidateSet covers every shipped tools/monitor/*.py."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVOKE = ROOT / "scripts" / "Invoke-JeevesMonitorCheck.ps1"
MONITOR = ROOT / "tools" / "monitor"

# ear_down_gate is a helper library imported by ircbob_ear (FR #9503), not a -Check.
SKIP = frozenset({"__init__", "_common", "ear_down_gate"})


def _shipped_checks() -> set[str]:
    out: set[str] = set()
    for path in MONITOR.glob("*.py"):
        stem = path.stem
        if stem in SKIP or stem.startswith("_"):
            continue
        out.add(stem)
    return out


def _validateset_names(text: str) -> set[str]:
    m = re.search(r"\[ValidateSet\(([^\)]*)\)\]", text, re.S)
    assert m, "ValidateSet missing"
    return set(re.findall(r"'([^']+)'", m.group(1)))


def test_fr9049_validateset_covers_shipped_monitor_py():
    text = INVOKE.read_text(encoding="utf-8")
    names = _validateset_names(text)
    shipped = _shipped_checks()
    missing = sorted(shipped - names)
    assert not missing, f"ValidateSet missing shipped checks: {missing}"
    for need in (
        "opencode_seats",
        "open_pr_stale_base",
        "open_pr_mrb_missing",
        "ticket_closure",
        "needs_human_false_positive",
        "wake_brief",
        "wake_grok_bot_bob",
    ):
        assert need in names


def test_fr9049_parameter_help_lists_wake_checks():
    text = INVOKE.read_text(encoding="utf-8")
    assert "wake_brief" in text
    assert "wake_grok_bot_bob" in text
