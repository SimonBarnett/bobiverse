"""FR #8403: recycleseat serialize stop+start and name the launch-failed reason.

When several recycleseat reqs are pending the tray must stop every seat first and
launch the replacements afterwards, so the 2-seat cap (and a concurrent launch) cannot
leave a stopped seat reporting ``launch-failed`` while a later Ensure path fills the gap
anonymously. A restore launch is net-zero and bypasses the cap (``-Restore``). When a
launch still returns no pid, the reason is named (seats-off / cap / worker-exe-missing),
never a bare ``launch-failed``. ``kind-unknown`` (no click record) stays a planned refuse.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLICK = ROOT / "tray" / "tools" / "BobTrayClickedSeats.ps1"
RECYCLE = ROOT / "tray" / "tools" / "BobTrayRecycleSeat.ps1"
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"


def _ps(script: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _recycle_script(root: Path, rdir: Path, log: Path, nicks, launch: str, extra: str = "") -> Path:
    lines = [
        f". '{CLICK}'",
        f". '{RECYCLE}'",
        "function Test-BobTraySeatsOff { $false }",
        "function Test-BobTrayPidAlive { param($ProcessId) $false }",
        "function Stop-BobWorkerSeatTrees { param($RootPids) $script:events.Add('stop:' + $RootPids[0]) }",
        "function Get-BobTraySeatMarkerPid { param($Nick) 0 }",
        "function Get-BobTraySeatPidFromNick { param($Nick) if ($Nick -match '-([0-9]+)$') { [int]$Matches[1] } else { 0 } }",
        "function Invoke-BobTrayRecycleSeatReportFailure { param($Root,$Site,$Exception) }",
        "$script:events = New-Object System.Collections.Generic.List[string]",
    ]
    for nick in nicks:
        lines.append(f"Add-BobTrayClickedSeat -Root '{root}' -Nick '{nick}' -Kind 'opencode' -Machine 'm'")
    if extra:
        lines.append(extra)
    lines.append(launch)
    lines.append(
        "$rows = @(Invoke-BobTrayRecycleSeatQueue -Root '{0}' -Dir '{1}' -Launch $launch -Log {{ param($m) }})".format(
            root, rdir
        )
    )
    lines.append(
        "$line = (@($script:events) -join ',') + '||' + (@($rows | ForEach-Object { $_.reason }) -join ',') + '||' + (@($rows | ForEach-Object { [string]$_.ok }) -join ',')"
    )
    lines.append(f"Set-Content -LiteralPath '{log}' -Value $line -Encoding ascii")
    script = log.parent / "run.ps1"
    script.write_text("\n".join(lines), encoding="ascii")
    return script


def _mkreqs(rdir: Path, nicks):
    rdir.mkdir(parents=True, exist_ok=True)
    expires = 4102444800
    for i, nick in enumerate(nicks):
        (rdir / f"req-{chr(97 + i)}.json").write_text(
            json.dumps({"id": chr(97 + i), "nick": nick, "by": "jeeves", "kind": "chair", "expires": expires}),
            encoding="ascii",
        )


def test_fr8403_serialize_stops_all_before_any_start(tmp_path: Path):
    root = tmp_path / "root"
    (root / "run").mkdir(parents=True)
    rdir = root / "run" / "recycleseat"
    nicks = ["m-11", "m-22", "m-33", "m-44"]
    _mkreqs(rdir, nicks)
    log = tmp_path / "out.txt"
    launch = "$launch = { param($seatNick, $kind, $model) $script:events.Add('start:' + $seatNick); return 5000 }"
    script = _recycle_script(root, rdir, log, nicks, launch)
    proc = _ps(script)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    got = log.read_text(encoding="ascii").strip()
    events, reasons, oks = got.split("||")
    assert events == "stop:11,stop:22,stop:33,stop:44,start:m-11,start:m-22,start:m-33,start:m-44", got
    assert reasons == "ok,ok,ok,ok", got
    assert oks == "True,True,True,True", got


def test_fr8403_launch_failed_names_cap(tmp_path: Path):
    root = tmp_path / "root"
    (root / "run").mkdir(parents=True)
    rdir = root / "run" / "recycleseat"
    _mkreqs(rdir, ["m-11"])
    log = tmp_path / "out.txt"
    launch = "$launch = { param($seatNick, $kind, $model) return 0 }"
    extra = "function Get-BobTrayWorkerCapRefusal { param($Mode) 'Max 2 workers (2 agent seats).' }"
    script = _recycle_script(root, rdir, log, ["m-11"], launch, extra)
    proc = _ps(script)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    got = log.read_text(encoding="ascii").strip()
    events, reasons, oks = got.split("||")
    assert reasons == "cap", got
    assert oks == "False", got


def test_fr8403_launch_failed_names_worker_exe_missing(tmp_path: Path):
    root = tmp_path / "root"
    (root / "run").mkdir(parents=True)
    rdir = root / "run" / "recycleseat"
    _mkreqs(rdir, ["m-11"])
    log = tmp_path / "out.txt"
    launch = "$launch = { param($seatNick, $kind, $model) return 0 }"
    script = _recycle_script(root, rdir, log, ["m-11"], launch)
    proc = _ps(script)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    got = log.read_text(encoding="ascii").strip()
    events, reasons, oks = got.split("||")
    assert reasons == "worker-exe-missing", got


def test_fr8403_kind_unknown_still_planned_refuse(tmp_path: Path):
    # No click record for m-99, so the recycle must refuse with kind-unknown (FR #7835)
    # and never launch a replacement (events stay empty).
    root = tmp_path / "root"
    (root / "run").mkdir(parents=True)
    rdir = root / "run" / "recycleseat"
    _mkreqs(rdir, ["m-99"])
    log = tmp_path / "out.txt"
    script = tmp_path / "run.ps1"
    script.write_text(
        "\n".join(
            [
                f". '{CLICK}'",
                f". '{RECYCLE}'",
                "function Test-BobTraySeatsOff { $false }",
                "function Test-BobTrayPidAlive { param($ProcessId) $false }",
                "function Stop-BobWorkerSeatTrees { param($RootPids) $script:events.Add('stop:' + $RootPids[0]) }",
                "function Get-BobTraySeatMarkerPid { param($Nick) 0 }",
                "function Get-BobTraySeatPidFromNick { param($Nick) 0 }",
                "function Invoke-BobTrayRecycleSeatReportFailure { param($Root,$Site,$Exception) }",
                "$script:events = New-Object System.Collections.Generic.List[string]",
                "$launch = { param($seatNick, $kind, $model) $script:events.Add('start:' + $seatNick); return 5000 }",
                f"$rows = @(Invoke-BobTrayRecycleSeatQueue -Root '{root}' -Dir '{rdir}' -Launch $launch -Log {{ param($m) }})",
                "$line = (@($script:events) -join ',') + '||' + (@($rows | ForEach-Object { $_.reason }) -join ',')",
                f"Set-Content -LiteralPath '{log}' -Value $line -Encoding ascii",
            ]
        ),
        encoding="ascii",
    )
    proc = _ps(script)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    got = log.read_text(encoding="ascii").strip()
    events, reasons = got.split("||")
    assert reasons == "kind-unknown", got
    assert events == "", got  # never launched


def test_fr8403_source_contract():
    recycle = RECYCLE.read_text(encoding="utf-8")
    watch = WATCH.read_text(encoding="utf-8")
    # restore launch bypasses the cap
    i = watch.index("function Start-BobTrayWorkerExe")
    # FR #9346: empty-online gate comments sit above the -Restore cap skip; keep a wide window.
    body = watch[i : i + 4500]
    assert "[switch]$Restore" in body
    assert "if (-not $Restore)" in body
    # the recycleseat Launch passes -Restore
    j = watch.index("Invoke-BobTrayRecycleSeatQueue")
    assert "-Restore" in watch[j:]
    # serialize + named refusal in the recycle helper
    assert "Get-BobTrayRecycleLaunchRefusal" in recycle
    assert "FR #8403" in recycle
    assert "kind-unknown" in recycle  # kept (FR #7835)
    assert "launch-failed" in recycle
    assert "worker-exe-missing" in recycle
