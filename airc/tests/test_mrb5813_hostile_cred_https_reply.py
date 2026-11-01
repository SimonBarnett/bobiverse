"""docs/mrb-5813: hostile pins for FR #5811 CRED persist via=https never silent."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

CMD = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-commands" / "SKILL.md"
TRO = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-troubleshooting" / "SKILL.md"
SVC = ROOT / "airc" / "scripts" / "airc_console_service.py"
PASSED = ROOT / "airc" / "scripts" / "airc_passed_cred.py"
CONSOLE = ROOT / "airc" / "scripts" / "airc_console.py"


def _window(text: str, needle: str, before: int = 80, after: int = 220) -> str:
    i = text.find(needle)
    assert i >= 0, needle
    return text[max(0, i - before) : i + after]


def test_mrb5813_on_line_dispatches_cred_contiguous():
    text = SVC.read_text(encoding="utf-8")
    win = _window(text, "FR #5811")
    assert "cred" in win
    assert "never go silent" in win or "must never go silent" in win
    # send-set membership near the FR marker
    assert '"cred"' in text or "'cred'" in text


def test_mrb5813_cred_fail_intake_contiguous():
    text = CONSOLE.read_text(encoding="utf-8")
    win = _window(text, "FR #5811: named reason", before=40, after=700)
    assert "report_verb_failure" in win
    assert '"cred"' in win or "'cred'" in win
    assert "has_url" in win
    assert "airc_fail_intake" in win


def test_mrb5813_non_json_body_mapping():
    text = PASSED.read_text(encoding="utf-8")
    assert "non-json-body" in text
    assert "JSONDecodeError" in text


def test_mrb5813_commands_skill_never_silent_window():
    text = CMD.read_text(encoding="utf-8")
    win = _window(text, "FR #5811")
    assert "action=cred" in win
    assert "never silent" in win
    assert "airc-cred-fail|" in win or "airc-cred-fail" in win
    assert "\u2014" not in text  # FR #3935 / #5818


def test_mrb5813_troubleshooting_silent_row():
    text = TRO.read_text(encoding="utf-8")
    assert "FR #5811" in text
    win = _window(text, "FR #5811")
    assert "action=cred" in win
    assert "cred-url-rejected" in win or "never silent" in win.lower()
