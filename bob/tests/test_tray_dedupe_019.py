"""v0.1.19 tray: #79 one row per machine (legacy alias folded), channel-ops wire BOM-safe/idempotent (real PowerShell 5.1)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from repo_layout import ROOT  # t773u: split repo; legacy flat paths resolve per service
TRAY = ROOT / "third_party" / "bob-tray"
PS = shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")
WATCH = TRAY / "tools" / "Watch-BobTray.ps1"
BOM = "\ufeff"


def _run(body: str, tmp_path: Path, env=None) -> list[str]:
    script = tmp_path / "t.ps1"
    script.write_bytes(("\ufeff$ErrorActionPreference='Stop'\r\n[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\r\n"
                        f"Import-Module '{TRAY / 'src' / 'BobBridge.psd1'}' -Force -DisableNameChecking\r\n"
                        "& (Get-Module BobBridge) {\r\n" + body + "\r\n}\r\n").encode("utf-8"))
    e = dict(os.environ)
    e["BOB_IRC_CONFIG"] = str(TRAY / "config" / "bobiverse.json")      # the shipped legacyAliases, whatever the host has set
    e.update(env or {})
    r = subprocess.run([PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                       capture_output=True, timeout=120, env=e)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    return r.stdout.decode("utf-8", "replace").splitlines()


@needs_ps
def test_canonical_id_folds_legacy_alias_and_dedupes_the_roster(tmp_path):
    out = _run("""
(Get-BobCanonicalMachineId 'ionos'), (Get-BobCanonicalMachineId ' IONOS '), (Get-BobCanonicalMachineId 'win-mpre8vi4u6u'),
(Get-BobCanonicalMachineId 'dev1'), (Get-BobCanonicalMachineId 'MarchHare'), (Get-BobCanonicalMachineId ([string][char]0xFEFF + 'flamingo')) | ForEach-Object { $_ }
'--'
(Select-BobUniqueCanonicalIds @('ionos','flamingo','win-mpre8vi4u6u','marchhare','IONOS','dev1')) -join ','
""", tmp_path)
    assert out[:6] == ["win-mpre8vi4u6u", "win-mpre8vi4u6u", "win-mpre8vi4u6u", "ce-priority-dev1", "marchhare", "flamingo"]
    assert out[-1] == "win-mpre8vi4u6u,flamingo,marchhare,ce-priority-dev1"


@needs_ps
def test_seat_period_end_cache_never_written_alias_keyed(tmp_path):
    bridge = tmp_path / "bridge"
    _run("""
Save-BobSeatPeriodEnd -MachineId 'ionos' -PeriodEnd '2026-10-04T00:36:16Z' -SeatId 'seat-a' -Weekly 40
""", tmp_path, {"BOB_BRIDGE_HOME": str(bridge)})
    doc = json.loads((bridge / "seat-period-end.json").read_text(encoding="utf-8-sig"))
    assert list(doc["by_machine"]) == ["win-mpre8vi4u6u"]
    assert list(doc["weekly_by_machine"]) == ["win-mpre8vi4u6u"]


@needs_ps
def test_channel_ops_wire_strips_bom_and_is_idempotent(tmp_path):
    home = tmp_path / "irchome"
    home.mkdir()
    (home / "channel-ops.json").write_bytes(
        (BOM + json.dumps({BOM + "#win-mpre8vi4u6u ": BOM + " bob-win-mpre8vi4u6u\r\n"})).encode("utf-8"))
    out = _run("""
$a = Sync-BobIrcChannelOpsWire
$b = Sync-BobIrcChannelOpsWire
$c = Sync-BobIrcChannelOpsWire
"first=" + (@($a.lines) -join '|')
"again=" + (@($b.lines).Count) + "," + (@($c.lines).Count)
""", tmp_path, {"BOB_IRC_HOME": str(home)})
    assert out[0] == "first=MODE #win-mpre8vi4u6u +o bob-win-mpre8vi4u6u"
    assert out[1] == "again=0,0"                              # not re-queued on every manifest sync
    box = (home / "outbox.txt").read_text(encoding="utf-8-sig")
    assert BOM not in box and box.count("MODE #win-mpre8vi4u6u +o bob-win-mpre8vi4u6u") == 1


@needs_ps
def test_read_json_file_tolerates_a_doubled_bom(tmp_path):
    p = tmp_path / "x.json"
    p.write_bytes((BOM + BOM + '{"a": 1}').encode("utf-8"))
    out = _run(f"(Read-JsonFile '{p}').a", tmp_path)
    assert out == ["1"]


def test_tile_code_dedupes_on_the_canonical_id():
    w = WATCH.read_text(encoding="utf-8-sig")
    sec = w[w.index("function Rebuild-BobTrayTiles"):w.index("Atomic swap on the TipForm")]
    assert "Get-BobCanonicalMachineId" in sec and "$shownMachines" in sec
    h = (TRAY / "src" / "Public" / "Get-BobTrayHover.ps1").read_text(encoding="utf-8-sig")
    assert "Select-BobUniqueCanonicalIds @($reportDigest.roster_machine_ids)" in h
    assert "$seatIds = @(Select-BobUniqueCanonicalIds" in h and "$ck -ne $k" in h
