"""MRB #6175 hostile: Format-BobOpencodePoolLine must not throw on non-numeric pct."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"


def test_format_opencode_uses_convert_to_int_or_null():
    src = HOVER.read_text(encoding="utf-8-sig")
    fn = src[src.index("function Format-BobOpencodePoolLine") : src.index("function Get-BobOpencodePaintFromDigest")]
    assert "ConvertTo-BobTrayIntOrNull" in fn
    assert "MRB #6175" in fn or "CodeRabbit" in fn


def test_format_opencode_non_numeric_returns_na_no_throw():
    """Behavioral: unknown/n/a strings must yield n/a bits without terminating the host."""
    ps = r"""
$ErrorActionPreference = 'Stop'
. '{hover}'
$cases = @(
  @( 'unknown', 50 ),
  @( 100, 'n/a' ),
  @( 'unknown', 'unknown' ),
  @( $null, $null ),
  @( 100, 50 )
)
foreach ($c in $cases) {{
  $r = Format-BobOpencodePoolLine -FreePct $c[0] -GoPct $c[1]
  if (-not $r) {{ throw 'empty result' }}
  Write-Output $r
}}
""".format(hover=str(HOVER).replace("'", "''"))
    script = Path(sys.executable).with_name("unused")
    # write temp ps1 beside pytest
    tmp = Path(__file__).with_name("_mrb6175_opencode_repro.ps1")
    tmp.write_text(ps, encoding="utf-8")
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-File", str(tmp)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    finally:
        if tmp.exists():
            tmp.unlink()
    assert proc.returncode == 0, proc.stderr or proc.stdout
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    assert any("n/a" in ln for ln in lines[:3]), lines
    assert lines[-1] == "OpenCode  go est 50%", lines
    # FR #7017: pool line is Go-only (free never painted).
    assert lines[0] == "OpenCode  go est 50%", lines
    assert lines[1] == "OpenCode  go n/a", lines
    assert lines[2] == "OpenCode  go n/a", lines
    assert lines[3] == "OpenCode  go n/a", lines