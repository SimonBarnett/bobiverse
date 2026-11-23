"""FR #9066: Invoke-JeevesMonitorCheck soft-skips missing tools/monitor/<check>.py.

Widen ValidateSet already on tip; missing .py must exit 0 with skipped JSON
(not Write-Error / exit 2). Path.parents IndexError covered by FR #8580 helpers.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import REPO

SCRIPTS = REPO / "jeeves" / "scripts"
INVOKE = SCRIPTS / "Invoke-JeevesMonitorCheck.ps1"

# Names that lagged live ValidateSet / AGENTS (issue #9066 / twin #9049).
WIDENED = (
    "opencode_seats",
    "open_pr_stale_base",
    "open_pr_mrb_missing",
    "ticket_closure",
    "needs_human_false_positive",
    "depends_on",
    "fr_digest",
)

WIN = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("powershell"),
    reason="needs Windows PowerShell",
)


def test_validate_set_includes_widened_checks():
    text = INVOKE.read_text(encoding="utf-8-sig")
    m = re.search(r"\[ValidateSet\(([^)]+)\)\]", text, re.S)
    assert m, "ValidateSet missing"
    names = {p.strip().strip("'\"") for p in m.group(1).split(",")}
    for name in WIDENED:
        assert name in names, f"ValidateSet missing {name}"


def test_needs_human_uses_ensure_script_dir_on_path():
    """Path.parents[N] IndexError on shallow J:\\tools\\monitor — use walk helper."""
    py = REPO / "jeeves" / "tools" / "monitor" / "needs_human_false_positive.py"
    text = py.read_text(encoding="utf-8")
    assert "ensure_script_dir_on_path" in text
    assert "parents[2]" not in text
    assert "parents[3]" not in text


@WIN
def test_soft_skip_missing_check_py(tmp_path: Path):
    """Empty InstallRoot: no tools\\monitor\\<check>.py → exit 0 + skipped JSON."""
    # InstallRoot with no tools/monitor/*.py
    root = tmp_path / "empty-install"
    root.mkdir()
    r = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(INVOKE),
            "-Check",
            "depends_on",
            "-InstallRoot",
            str(root),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, f"stderr={r.stderr!r} stdout={r.stdout!r}"
    lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    assert lines, f"expected JSON line; stderr={r.stderr!r}"
    payload = json.loads(lines[-1])
    assert payload.get("ok") is True
    assert payload.get("skipped") is True
    assert payload.get("check") == "depends_on"
    reason = str(payload.get("reason") or "")
    assert "missing" in reason.lower()
    assert "depends_on.py" in reason
