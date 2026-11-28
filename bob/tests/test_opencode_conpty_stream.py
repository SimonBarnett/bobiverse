"""OpenCode capture must grow before the child exits."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

RUNNER = Path(__file__).resolve().parents[1] / "scripts" / "opencode_conpty_run.py"


def test_conpty_writes_before_child_exits(tmp_path: Path):
    out = tmp_path / "out.txt"
    err = tmp_path / "err.txt"
    argv_file = tmp_path / "argv.json"
    child = (
        "import sys,time; sys.stdout.write('hello\\n'); sys.stdout.flush(); time.sleep(2); sys.stdout.write('bye\\n'); sys.stdout.flush()"
    )
    argv_file.write_text(json.dumps([sys.executable, "-c", child]), encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(RUNNER), "--out", str(out), "--err", str(err), "--cwd", str(tmp_path), "--argv-file", str(argv_file)]
    )
    try:
        deadline = time.time() + 8
        seen = ""
        while time.time() < deadline and proc.poll() is None:
            if out.exists():
                seen = out.read_text(encoding="utf-8", errors="replace")
                if "hello" in seen:
                    break
            time.sleep(0.05)
        assert "hello" in seen
        assert proc.poll() is None
    finally:
        proc.wait(timeout=15)
