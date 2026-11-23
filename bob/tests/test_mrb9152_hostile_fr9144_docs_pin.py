# -*- coding: utf-8 -*-
"""MRB #9152 hostile: monitoring.md documents ircbob_ear (FR #9144)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MONITORING = ROOT / "jeeves" / "docs" / "monitoring.md"


def test_mrb9152_monitoring_documents_ircbob_ear():
    text = MONITORING.read_text(encoding="utf-8")
    assert "## ircbob_ear (FR #9144)" in text
    assert "digest ear-offline:" in text
    assert "digest unreachable:" in text
    assert "Start-Service" in text
    assert "Never touches Ergo" in text or "never touches Ergo" in text.lower()
