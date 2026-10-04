r"""FR #1704: the agent-folder skill sync must rewrite only a bare `.\scripts\`, never the tail of `..\scripts\`.

`$t.Replace('.\scripts\', '..\scripts\')` turned an already-correct `..\scripts\` into `...\scripts\`
(broken Clear-BobiverseJobWorktrees path in the installed worker skills). Also pins the PowerShell BOMs
(a double-encoded BOM `ï»¿` made Pack-BobiverseRelease.ps1 unparsable on Windows PowerShell 5.1).
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
MOJIBAKE_BOM = bytes.fromhex("c3afc2bbc2bf")


def _rewrite_expr() -> str:
    text = COMMON.read_text(encoding="utf-8-sig")
    m = re.search(r"\$t2 = (\[regex\]::Replace\(\$t, .*?'\.\.\\scripts\\'\))", text)
    assert m, "skill sync no longer uses the guarded regex rewrite"
    assert ".Replace('.\\scripts\\', '..\\scripts\\')" not in text
    return m.group(1)


@pytest.mark.skipif(sys.platform != "win32", reason="runs Windows PowerShell")
def test_skill_scripts_path_rewrite_does_not_triple_the_dot():
    expr = _rewrite_expr()
    sample = r"A .\scripts\Report.ps1 B ..\scripts\Clear-BobiverseJobWorktrees.ps1 C `.\scripts\X.ps1`"
    ps = "$t = '" + sample.replace("'", "''") + "'; " + expr + " | Write-Output"
    run = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    out = run.stdout.strip()
    assert "...\\scripts\\" not in out, out
    assert out.count("..\\scripts\\") == 3, out
    assert ".\\scripts\\Report.ps1" not in out.replace("..\\scripts\\", ""), out


def test_powershell_sources_have_no_double_encoded_bom():
    bad = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*.ps1")
           if "docs" not in p.relative_to(ROOT).parts[:2] and ".git" not in p.parts
           and p.read_bytes()[:6] == MOJIBAKE_BOM]
    assert not bad, f"double-encoded BOM (ï»¿) in: {bad}"