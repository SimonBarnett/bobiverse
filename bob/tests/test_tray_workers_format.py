"""v0.1.18 tray: worker lines, stale periods hidden, fleet Cursor values once, UTF-8 decode (real PowerShell 5.1)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import bobreport
import registered_machines as rm

from repo_layout import ROOT  # t773u: split repo; legacy flat paths resolve per service
TRAY = ROOT / "third_party" / "bob-tray"
PS = shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")
HOVER = TRAY / "src" / "Public" / "Get-BobTrayHover.ps1"
WATCH = TRAY / "tools" / "Watch-BobTray.ps1"
IRC = TRAY / "src" / "Private" / "Get-BobIrc.ps1"


def _run(body: str, tmp_path: Path) -> list[str]:
    script = tmp_path / "t.ps1"
    script.write_bytes(("\ufeff$ErrorActionPreference='Stop'\r\n[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\r\n"
                        f"Import-Module '{TRAY / 'src' / 'BobBridge.psd1'}' -Force -DisableNameChecking\r\n"
                        "& (Get-Module BobBridge) {\r\n" + body + "\r\n}\r\n").encode("utf-8"))
    r = subprocess.run([PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                       capture_output=True, timeout=120)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    return r.stdout.decode("utf-8", "replace").splitlines()


def _txt(p):
    return p.read_text(encoding="utf-8-sig")


# ---------------------------------------------------------------------------------- static
def test_grok_account_rows_show_only_worker_lines_no_cursor_values():
    w = _txt(WATCH)
    sec = w[w.index("-Title 'Grok accounts'"):w.index("$script:tileHost.Height = [Math]::Max(10, $y)")]
    for gone in ("grok_pools", "cursor_pools", "overspend", "not in moot", "no jobs", "lastSeen stale", "up since", "$m.jobs"):
        assert gone not in sec, gone
    assert "$m.worker_lines" in sec
    # the fleet Cursor section (with the single overspend line) is above, once
    top = w[:w.index("-Title 'Grok accounts'")]
    assert top.count("-RightText $overLine") == 1


def test_no_raw_non_ascii_literal_left_in_pool_heading_code():
    h = _txt(HOVER)
    fn = h[h.index("function Format-BobCursorControlPoolHeading"):h.index("function Select-BobCursorGroupRemainMinimum")]
    assert all(ord(c) < 128 for c in fn), "non-ASCII literal would be mis-decoded by Windows PowerShell 5.1"
    assert "[char]0x00B7" in fn


def test_digest_is_read_as_utf8_bytes_not_latin1_content():
    irc, w = _txt(IRC), _txt(WATCH)
    assert "function ConvertFrom-BobUtf8Json" in irc and "RawContentStream" in irc and "UTF8.GetString" in irc
    assert "$resp.Content | ConvertFrom-Json" not in irc
    assert "Invoke-RestMethod -Uri (Get-BobTrayDigestReportUrl) -TimeoutSec 8" not in w
    assert "RawContentStream" in w


# ---------------------------------------------------------------------------------- behaviour
@needs_ps
def test_worker_line_format_is_exactly_nick_colon_doing_or_idle(tmp_path):
    out = _run("""
Format-BobTrayWorkerLine ([pscustomobject]@{nick='marchhare-101';state='doing';work='FR o/r#5 fix the thing'})
Format-BobTrayWorkerLine ([pscustomobject]@{nick='marchhare-102';state='idle';work=''})
Format-BobTrayWorkerLine ([pscustomobject]@{nick='marchhare-103';state='idle';work='stale text'})
Format-BobTrayWorkerLine ([pscustomobject]@{nick='marchhare-104';state='doing';work="two`nlines"})
Format-BobTrayWorkerLine ([pscustomobject]@{nick='marchhare-105';state='offered';work='bobiverse UAT #629'})
""", tmp_path)
    assert out == ["marchhare-101: FR o/r#5 fix the thing", "marchhare-102: idle", "marchhare-103: idle",
                   "marchhare-104: two lines", "marchhare-105: offered: bobiverse UAT #629"]


@needs_ps
def test_stale_period_is_unknown_and_hidden_future_period_is_kept(tmp_path):
    out = _run("""
$past = ([datetime]::UtcNow.AddDays(-3)).ToString('o'); $fut = ([datetime]::UtcNow.AddDays(2).AddHours(3)).ToString('o')
$a = Resolve-BobTrayLivePeriod -Pct 91 -PeriodEnd $past
'stale|{0}|{1}|{2}' -f $a.pct, $a.period_end, $a.reset_label
$b = Resolve-BobTrayLivePeriod -Pct 0 -PeriodEnd $fut
'live|{0}|{1}' -f $b.pct, $b.reset_label
$c = Resolve-BobTrayLivePeriod -Pct 40 -PeriodEnd $null
'noend|{0}|{1}' -f $c.pct, $c.reset_label
'label|' + (Format-BobResetLabel -PeriodEnd $past)
""", tmp_path)
    assert out[0] == "stale|||"                              # pct, end and label all unknown
    assert out[1] == "live|0|2 days, 2 hours" and out[2] == "noend|40|"
    assert out[3] == "label|"                                # no clamped "0 minutes" for an ended period


@needs_ps
def test_pool_heading_uses_char_code_middle_dot(tmp_path):
    out = _run("""
$h = Format-BobCursorControlPoolHeading -GroupLabel 'Cursor Models' -PctLabel '0%' -ResetLabel '15 days'
($h.ToCharArray() | ForEach-Object { [int]$_ }) -join ','
""", tmp_path)
    codes = [int(x) for x in out[-1].split(",")]
    assert 183 in codes and 194 not in codes                 # U+00B7, never A-circumflex (U+00C2)


@needs_ps
def test_utf8_digest_with_dot_decodes_even_when_decoded_as_latin1(tmp_path):
    out = _run("""
$json = '{"machines":{"marchhare":{"workers":[{"nick":"marchhare-1","state":"doing","work":"FR caf' + [char]0xE9 + ' ' + [char]0xB7 + ' fix"}]}}}'
$bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
$resp = [pscustomobject]@{ RawContentStream = (New-Object System.IO.MemoryStream (, $bytes)); Content = [System.Text.Encoding]::GetEncoding(28591).GetString($bytes) }
$j = ConvertFrom-BobUtf8Json -Response $resp
($j.machines.marchhare.workers[0].work.ToCharArray() | ForEach-Object { [int]$_ }) -join ','
$resp2 = [pscustomobject]@{ Content = [System.Text.Encoding]::GetEncoding(28591).GetString($bytes) }   # no stream: repair path
$j2 = ConvertFrom-BobUtf8Json -Response $resp2
($j2.machines.marchhare.workers[0].work.ToCharArray() | ForEach-Object { [int]$_ }) -join ','
""", tmp_path)
    for line in out[-2:]:
        codes = [int(x) for x in line.split(",")]
        assert 183 in codes and 233 in codes and 194 not in codes and 195 not in codes


@needs_ps
def test_real_digest_from_jeeves_renders_worker_lines_per_machine(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rm.sync_from_chanserv(tmp_path, ["#bobiverse", "#marchhare", "#win-mpre8vi4u6u"])
    for p in ({"op": "worker-upsert", "machine": "marchhare", "nick": "marchhare-102"},
              {"op": "worker-work", "machine": "marchhare", "nick": "marchhare-101", "state": "doing",
               "work": "FR o/r#5 caf\u00e9 \u00b7 fix"}):
        assert bobreport.apply_callback(tmp_path, p).ok
    d = tmp_path / "digest-out.json"
    d.write_text(json.dumps(bobreport.build_digest_object(tmp_path, "Jeeves"), ensure_ascii=False), encoding="utf-8")
    out = _run(f"""
$doc = [System.IO.File]::ReadAllText('{d}', [System.Text.Encoding]::UTF8) | ConvertFrom-Json
foreach ($w in @(Get-BobTrayDigestWorkers -Digest $doc -MachineId 'MARCHHARE')) {{ Format-BobTrayWorkerLine -Worker $w }}
'other=' + @(Get-BobTrayDigestWorkers -Digest $doc -MachineId 'win-mpre8vi4u6u').Count
""", tmp_path)
    assert out == ["marchhare-101: FR o/r#5 caf\u00e9 \u00b7 fix", "marchhare-102: idle", "other=0"]
