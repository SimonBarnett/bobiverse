"""docs/mrb-6411: hello ready line only after successful start_agent (CodeRabbit on #6411)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bob" / "scripts"))
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import bob_worker as bw  # noqa: E402


def _run_agent_src() -> str:
    src = (ROOT / "bob" / "scripts" / "bob_worker.py").read_text(encoding="utf-8")
    i = src.find("def run_agent(")
    assert i >= 0, "run_agent missing"
    return src[i:]


def test_hello_send_after_successful_start_agent():
    """Hostile pin: worker_hello_line call must follow start_agent success gate."""
    chunk = _run_agent_src()
    i_start = chunk.find("if not sup.start_agent()")
    i_hello = chunk.find("worker_hello_line(kind, build=build)")
    assert i_start >= 0, "start_agent gate missing"
    assert i_hello >= 0, "hello send missing"
    assert i_hello > i_start, "hello must not claim ready before start_agent succeeds"
    # Launch-fail path returns before hello.
    fail_return = chunk.find("return EXIT_LAUNCH_FAIL", i_start)
    assert 0 <= fail_return < i_hello


def test_worker_hello_line_docstring_after_start():
    assert "successful agent start" in (bw.worker_hello_line.__doc__ or "")


def test_docs_say_no_ready_on_launch_fail():
    text = (ROOT / "bob" / "docs" / "bob-worker.md").read_text(encoding="utf-8")
    assert "successful agent launch" in text
    assert "no ready claim when launch fails" in text
    assert "worker_build=" in text
