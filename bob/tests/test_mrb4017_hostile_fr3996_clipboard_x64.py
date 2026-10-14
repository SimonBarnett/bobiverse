"""Hostile MRB #4017 / FR #3996: x64 clipboard ctypes + batched KEY fallback."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

SRC = ROOT / "scripts" / "bob_worker.py"


def test_mrb4017_hostile_configure_before_global_alloc():
    text = SRC.read_text(encoding="utf-8")
    i_set = text.index("def _clipboard_set_unicode")
    chunk = text[i_set : i_set + 2500]
    assert "_configure_clipboard_winapi(k32, u32)" in chunk
    assert chunk.index("_configure_clipboard_winapi(k32, u32)") < chunk.index("GlobalAlloc")


def test_mrb4017_hostile_no_hard_fail_without_batch_fallback():
    text = SRC.read_text(encoding="utf-8")
    # Long paste-preferred path must not return False solely for clipboard without keys fallback.
    assert "reason=clipboard_fallback" in text
    assert "build_key_records(text" in text
    assert "no KEY_EVENT drip; batched" in text


def test_mrb4017_hostile_skill_mentions_3996():
    skill = ROOT / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    assert "FR #3996" in text or "#3996" in text
    assert "clipboard_fallback" in text or "batched" in text.lower()
