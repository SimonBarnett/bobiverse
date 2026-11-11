"""Hostile pins for MRB #6625 / FR #6586 incremental suite logs.

Additive: product already streams with flush and rewrites failed-tests.txt.
These pins lock the fold with FR #6585 (``_print_progress`` vs ``_progress()``).
"""
from __future__ import annotations

import inspect
from pathlib import Path

import bobiverse_build as bb

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "common" / "scripts" / "bobiverse_build.py"
IRC = ROOT / "common" / "scripts" / "irc_agent.py"


def test_mrb6625_run_command_accepts_log_path():
    sig = inspect.signature(bb.run_command)
    assert "log_path" in sig.parameters


def test_mrb6625_print_progress_distinct_from_poster_accessor():
    text = SRC.read_text(encoding="utf-8")
    assert "def _print_progress(self, msg: str)" in text
    assert "def _progress(self) -> BuildProgressPoster | None" in text
    assert "def _write_failed_tests_summary" in text
    assert "failed-tests.txt" in text
    # Must not redefine _progress(msg) which would shadow the poster accessor.
    assert "def _progress(self, msg: str)" not in text


def test_mrb6625_ear_runner_log_line_buffered():
    text = IRC.read_text(encoding="utf-8")
    assert "buffering=1" in text or "bufsize=1" in text
