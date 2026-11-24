# -*- coding: utf-8 -*-
"""FR #9750: TipForm paints digest.copilot.tasks once under the Copilot pool row."""
from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
DIALOGS = ROOT / "tray" / "tools" / "BobTrayDialogs.ps1"
STATUS_CS = ROOT / "tray" / "dialogs" / "BobStatus.cs"
DOCS = ROOT / "docs" / "bob-tray-dialogs.md"
PS = shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr9750_formatter_exists_and_pins_contract():
    h = _txt(HOVER)
    assert "function Format-BobCopilotTaskLines" in h
    assert "FR #9750" in h
    fmt = h[
        h.index("function Format-BobCopilotTaskLines") : h.index(
            "function Get-BobCopilotMeterBarPct"
        )
    ]
    assert "working_on" in fmt
    assert "model" in fmt
    assert "machines.copilot" not in fmt.lower() or "never" in fmt.lower()


def test_fr9750_hover_exports_task_lines():
    h = _txt(HOVER)
    # Export on the hover object after pool fields.
    assert "copilot_task_lines" in h
    assert "Format-BobCopilotTaskLines" in h
    # Soft-allow #9748: read nested digest.copilot.tasks (not machines.copilot).
    assert ".tasks" in h or "copilot.tasks" in h or "Pool.tasks" in h or "$copilotPoolObj.tasks" in h


def test_fr9750_rebuild_paints_after_pool_usage_row():
    w = _txt(WATCH)
    assert "CopilotTaskLines" in w
    sec = w[w.index("FR #5172") : w.index("$indent = 18")]
    assert "FR #9750" in sec or "CopilotTaskLines" in sec
    # After the pool UsageRow, before digest-pool extras / machine indent block.
    pool_row = sec.index("-Heading $copilotLine")
    assert "CopilotTaskLines" in sec[pool_row:]
    # Must not invent a synthetic machines.copilot seat for this paint.
    assert "machines.copilot" not in sec.lower()
    assert "Family 'copilot'" in sec


def test_fr9750_update_hover_passes_task_lines():
    w = _txt(WATCH)
    assert "-CopilotTaskLines" in w or "CopilotTaskLines @" in w or "CopilotTaskLines @(" in w


def test_fr9750_status_model_and_paint():
    d = _txt(DIALOGS)
    assert "copilot_task_lines" in d
    cs = _txt(STATUS_CS)
    assert "FR #9750" in cs or "CopilotTaskLines" in cs
    assert "machines.copilot" not in cs.lower()


def test_fr9750_docs_pin():
    d = _txt(DOCS)
    assert "FR #9750" in d
    assert "copilot.tasks" in d or "digest.copilot.tasks" in d


@needs_ps
def test_fr9750_format_task_lines_behaviour(tmp_path: Path):
    script = tmp_path / "fr9750_fmt.ps1"
    script.write_text(
        textwrap.dedent(
            f"""
            $ErrorActionPreference = 'Stop'
            . '{HOVER}'
            $empty = @(Format-BobCopilotTaskLines -Tasks $null)
            if ($empty.Count -ne 0) {{ throw ('empty={{0}}' -f ($empty -join '|')) }}

            $lines = @(Format-BobCopilotTaskLines -Tasks @(
                [pscustomobject]@{{
                    model = 'claude-haiku-4.5'
                    working_on = 'FR #9748'
                    task = 'FR'
                    id = '#9748'
                }}
                [pscustomobject]@{{
                    start_model = 'gpt-6-luna'
                    task = 'MRB'
                    id = '#99'
                }}
                [pscustomobject]@{{
                    model = ''
                    working_on = ''
                    task = ''
                    id = ''
                }}
            ))
            if ($lines.Count -ne 2) {{ throw ('count={{0}} lines={{1}}' -f $lines.Count, ($lines -join '|')) }}
            if ($lines[0] -ne 'claude-haiku-4.5: FR #9748') {{ throw ('l0={{0}}' -f $lines[0]) }}
            if ($lines[1] -ne 'gpt-6-luna: MRB #99') {{ throw ('l1={{0}}' -f $lines[1]) }}
            Write-Output 'ok'
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, (r.stdout or "") + "\n" + (r.stderr or "")
    assert "ok" in (r.stdout or "")
