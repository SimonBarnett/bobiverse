"""FR #6267: TipForm fleet Cursor/xAI weekly is digest-only.

Observed: MARCHHARE - ntsa (43%) while public digest machines.marchhare had
weekly/pcent/cursor_pools at 74-75 and account bob-marchhare. Peer peek /
peCache / seat-min must not paint a non-digest % when a digest is present.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
DOCS = ROOT / "docs" / "bob-tray-dialogs.md"
PS = shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr6267_helpers_and_digest_lock_pins():
    h = _txt(HOVER)
    assert "FR #6267" in h
    assert "function Select-BobTrayFleetWeeklyPct" in h
    assert "function Resolve-BobTrayDigestAccountLabel" in h
    assert "digestWeeklyLocked" in h
    # Peer peek must not overwrite digest-locked weekly.
    peek = h[h.index("Read-BobPeerPeek") : h.index("Durable fallback: seat-period-end.json")]
    assert "digestWeeklyLocked" in peek
    assert "FR #6267" in peek
    # Seat-min must not paint a peer digest min onto a known local weekly (AgentMonitor#150).
    seat_min = h[h.index("Same xAI seat => one shared remaining %") : h.index("Durable fallback: seat-period-end.json")]
    assert "never seat-min a peer digest % onto a known local weekly" in seat_min
    assert "if ($smid -eq $machineId -and $localWeeklyLocked) { continue }" in seat_min
    # peCache peer fill gated when digest present / locked.
    pec = h[h.index("Durable fallback: seat-period-end.json") : h.index("t785u: this host")]
    assert "FR #6267" in pec
    assert "digestWeeklyLocked" in pec or "reportDigest" in pec


def test_fr6267_docs_note_digest_only_fleet_weekly():
    assert DOCS.is_file()
    d = _txt(DOCS)
    assert "FR #6267" in d
    assert "digest-only" in d.lower() or "digest only" in d.lower()


@needs_ps
def test_fr6267_digest_74_beats_local_or_peek_43(tmp_path: Path):
    """Behavioral: digest MarchHare 74 + non-digest 43 => paint 74, source=digest, account from digest."""
    script = tmp_path / "fr6267.ps1"
    script.write_text(
        textwrap.dedent(
            f"""
            $ErrorActionPreference = 'Stop'
            . '{HOVER}'
            $sel = Select-BobTrayFleetWeeklyPct -DigestWeeklyPct 74 -NonDigestPct 43 -DigestPresent
            if ($sel.remaining_pct -ne 74) {{ throw ("pct={{0}}" -f $sel.remaining_pct) }}
            if ($sel.source -ne 'digest') {{ throw ("source={{0}}" -f $sel.source) }}
            $unknown = Select-BobTrayFleetWeeklyPct -DigestWeeklyPct $null -NonDigestPct 43 -DigestPresent
            if ($null -ne $unknown.remaining_pct) {{ throw 'unknown must not fall back to 43' }}
            if ($unknown.source -ne 'none') {{ throw ("unknown source={{0}}" -f $unknown.source) }}
            $ent = [pscustomobject]@{{
                nick = 'bob-marchhare'
                cursor_pools = @(
                    [pscustomobject]@{{ id = 'grok-weekly'; remaining = 74; account = 'bob-marchhare' }}
                )
            }}
            $seat = [pscustomobject]@{{ id = 'ntsa'; label = 'ntsa'; email = 'si@ntsa.uk' }}
            $label = Resolve-BobTrayDigestAccountLabel -DigestEnt $ent -SeatInfo $seat
            if ($label -ne 'bob-marchhare') {{ throw ("label={{0}}" -f $label) }}
            # Seat-min apply guard: local lock must skip overwrite (pin source phrase).
            $hover = Get-Content -LiteralPath '{HOVER}' -Raw
            if ($hover -notmatch 'never seat-min a peer digest % onto a known local weekly') {{
                throw 'missing local seat-min guard comment'
            }}
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
    assert r.returncode == 0, r.stdout + "\n" + r.stderr
    assert "ok" in (r.stdout or "")
