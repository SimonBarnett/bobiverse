"""MRB #6244 fix: provider-limits Python passed via powershell.exe -c must use single quotes.

Windows PowerShell 5.1 strips embedded double quotes from native -c arguments.
bobreport launches Get-BobOpencodeFuel with powershell.exe, so double-quoted
os.environ.get(\"...\") becomes a NameError/SyntaxError and every provider window
is unknown. The stats path already documents this; the limits path must match.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FUEL_PS1 = ROOT / "tray" / "tools" / "Get-BobOpencodeFuel.ps1"


def _limits_script_body(src: str) -> str:
    m = re.search(
        r"\$limitsScript\s*=\s*@'(.*?)'\@",
        src,
        flags=re.DOTALL,
    )
    assert m, "limitsScript here-string not found"
    return m.group(1)


def test_limits_script_has_no_double_quotes():
    src = FUEL_PS1.read_text(encoding="utf-8-sig")
    body = _limits_script_body(src)
    assert '"' not in body, (
        "limitsScript must use only single-quoted Python literals for WinPS 5.1 -c "
        f"(found double quote in: {body!r})"
    )
    assert "os.environ.get('BOB_OPENCODE_PROVIDER_PREVIOUS')" in body
    assert "os.environ.get('BOB_OPENCODE_USAGE_URL')" in body
    assert "{'provider_read'" in body or "{'provider_read':" in body


@pytest.mark.skipif(sys.platform != "win32", reason="powershell.exe host-only")
def test_limits_script_runs_under_powershell_51_c():
    """Behavioral: powershell.exe -c of the tip limitsScript must not SyntaxError."""
    src = FUEL_PS1.read_text(encoding="utf-8-sig")
    body = _limits_script_body(src).strip()
    # Stub opencode_fuel so we do not need a live usage URL.
    stub = (
        "import sys, types\n"
        "m = types.ModuleType('opencode_fuel')\n"
        "m.fetch_usage_limits = lambda *a, **k: {'kind': 'ok'}\n"
        "m.windows_from_usage_read = lambda *a, **k: "
        "{'rolling': {'status': 'ok'}, 'week': {'status': 'ok'}, 'month': {'status': 'ok'}}\n"
        "sys.modules['opencode_fuel'] = m\n"
    )
    py_src = stub + "\n" + body
    ps = (
        f"$py = '{sys.executable.replace(chr(39), chr(39)+chr(39))}'\n"
        f"$s = @'\n{py_src}\n'@\n"
        "& $py -c $s\n"
    )
    tmp = Path(__file__).with_name("_mrb6244_ps51_limits_repro.ps1")
    tmp.write_text(ps, encoding="utf-8")
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-File", str(tmp)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    finally:
        if tmp.exists():
            tmp.unlink()
    assert proc.returncode == 0, proc.stderr or proc.stdout
    out = (proc.stdout or "").strip()
    assert "provider_read" in out, out
    assert "SyntaxError" not in (proc.stderr or "")
