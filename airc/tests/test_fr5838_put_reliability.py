"""FR #5838: explicit PUT completion, bounded resend lists and relay-safe pacing."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import airc_jobs as jobs
import irc_agent as irc
from repo_layout import ROOT


NICK = "bob-tm"
JID = "aabbccdd"
SCRIPT = ROOT / "airc" / "scripts" / "Invoke-AircRemote.ps1"
PS = os.environ.get("AIRC_POWERSHELL") or shutil.which("pwsh") or shutil.which("powershell")


def _begin(tmp_path, data=b"abc"):
    store = jobs.JobStore(tmp_path)
    proto = jobs.JobProtocol(store)
    dest = store.drop_root / "payload.bin"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"old")
    assert proto.handle(NICK, "PUT", {
        "id": JID, "path": "payload.bin", "bytes": str(len(data)),
        "sha256": hashlib.sha256(data).hexdigest(),
    })[0].startswith("ok ")
    return store, proto, dest


def _chunk(proto, seq, data):
    return proto.handle(NICK, "CHUNK", {
        "id": JID, "seq": str(seq), "data": base64.b64encode(data).decode("ascii"),
    })


@pytest.mark.parametrize("seqs", [None, ""])
@pytest.mark.parametrize("data", [b"abc", b""])
def test_missing_seqs_is_one_named_error_and_repairable(tmp_path, seqs, data):
    store, proto, dest = _begin(tmp_path, data)
    if data:
        _chunk(proto, 1, data)
    kv = {"id": JID}
    if seqs is not None:
        kv["seqs"] = seqs
    assert proto.handle(NICK, "PUTEND", kv) == [
        f"err id={JID} code=put-seqs-required msg=PUTEND requires seqs=N"
    ]
    assert dest.read_bytes() == b"old"
    assert store._meta[JID].state == "receiving"
    assert proto.handle(NICK, "PUTEND", {"id": JID, "seqs": "1" if data else "0"})[0].startswith(
        f"ok id={JID} putend "
    )
    assert dest.read_bytes() == data


@pytest.mark.parametrize("seqs", ["-1", "nope", str(jobs.MAX_PUT_BYTES + 1)])
def test_invalid_counts_are_bounded_and_do_not_place(tmp_path, seqs):
    store, proto, dest = _begin(tmp_path)
    assert "code=bad_frame" in proto.handle(NICK, "PUTEND", {"id": JID, "seqs": seqs})[0]
    assert dest.read_bytes() == b"old"
    assert store._meta[JID].state == "receiving"


def test_gap_resend_preserves_state_and_places_only_when_complete(tmp_path):
    store, proto, dest = _begin(tmp_path)
    _chunk(proto, 3, b"c")
    _chunk(proto, 1, b"a")
    replies = proto.handle(NICK, "PUTEND", {"id": JID, "seqs": "3"})
    assert len(replies) == 1
    assert "code=order msg=missing=2 missing_more=0 " in replies[0]
    assert dest.read_bytes() == b"old"
    assert store._meta[JID].state == "receiving"
    _chunk(proto, 2, b"b")
    assert "dup=1" in _chunk(proto, 1, b"a")[0]
    assert "putend bytes=3" in proto.handle(NICK, "PUTEND", {"id": JID, "seqs": "3"})[0]
    assert dest.read_bytes() == b"abc"
    assert "already=1" in proto.handle(NICK, "PUTEND", {"id": JID})[0]


def test_resend_list_is_bounded_and_includes_dropped_tail(tmp_path):
    _, proto, dest = _begin(tmp_path, b"x" * 40)
    _chunk(proto, 1, b"x")
    reply = proto.handle(NICK, "PUTEND", {"id": JID, "seqs": "40"})[0]
    assert f"missing={','.join(str(i) for i in range(2, 18))} missing_more=23 " in reply
    assert len(reply.encode("utf-8")) < 400
    assert dest.read_bytes() == b"old"
    for seq in range(2, 40):
        _chunk(proto, seq, b"x")
    assert "missing=40 missing_more=0 " in proto.handle(
        NICK, "PUTEND", {"id": JID, "seqs": "40"}
    )[0]


def test_unexpected_sequences_are_not_accepted(tmp_path):
    _, proto, dest = _begin(tmp_path)
    _chunk(proto, 4, b"abc")
    assert "code=order" in proto.handle(NICK, "PUTEND", {"id": JID, "seqs": "0"})[0]
    assert dest.read_bytes() == b"old"


@pytest.mark.parametrize("body", [
    f"err id={JID} code=put-seqs-required msg=PUTEND requires seqs=N",
    f"err id={JID} code=order msg=missing=2 missing_more=0",
    f"ok id={JID} putend bytes=3 sha256={'a' * 64}",
])
def test_ear_captures_put_results_only_from_console(tmp_path, body):
    assert irc.is_airc_console_reply("tm_console", body)
    assert not irc.is_airc_console_reply("other", body)
    irc.append_airc_reply_jsonl(tmp_path, "tm_console", body)
    assert json.loads((tmp_path / "airc-replies.jsonl").read_text())["body"] == body


@pytest.mark.skipif(not PS, reason="PowerShell is required for remote helper tests")
def test_remote_helper_put_completion_errors_and_pacing(tmp_path):
    # Load only existing helper functions, leaving the remote entry point offline.
    command = r"""
    $ErrorActionPreference = 'Stop'
    Set-StrictMode -Version Latest
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($env:TEST_SCRIPT, [ref]$null, [ref]$null)
    foreach ($fn in $ast.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst]}, $false)) {
        . ([scriptblock]::Create($fn.Extent.Text))
    }
    function Assert-Test($ok) { if (-not $ok) { throw 'FR5838 assertion failed' } }
    $id = 'aabbccdd'
    $jsonl = Join-Path $env:TEST_TMP 'replies.jsonl'
    $ack = "ok id=$id putend bytes=3 sha256=aaaa via=dcc"
    Add-Content $jsonl (@{ body = $ack } | ConvertTo-Json -Compress)
    $lines = @(Wait-AircRemoteReplies -RepliesJsonl $jsonl -ExpectJobId $id -TimeoutSec 1)
    $parsed = ConvertFrom-AircRemoteReply -Lines $lines -ExpectJobId $id
    Assert-Test ($parsed.ExitCode -eq 0 -and $parsed.Bytes -eq 3 -and $parsed.Via -eq 'dcc')
    foreach ($errorBody in @("err id=$id code=put-seqs-required msg=seqs=N", "err id=$id code=order msg=missing=2 missing_more=0")) {
        Set-Content $jsonl (@{ body = 'err id=deadbeef code=order msg=missing=1' } | ConvertTo-Json -Compress)
        Add-Content $jsonl (@{ body = $errorBody } | ConvertTo-Json -Compress)
        try {
            Wait-AircRemoteReplies -RepliesJsonl $jsonl -ExpectJobId $id -TimeoutSec 1 | Out-Null
            throw 'expected protocol error'
        } catch { Assert-Test ([string]$_ -match [regex]::Escape($errorBody)) }
        try {
            ConvertFrom-AircRemoteReply -Lines @($errorBody) -ExpectJobId $id | Out-Null
            throw 'expected protocol error'
        } catch { Assert-Test ([string]$_ -match [regex]::Escape($errorBody)) }
    }
    $parsed = ConvertFrom-AircRemoteReply -Lines @('err id=deadbeef code=order', "DONE id=$id exit=0") -ExpectJobId $id
    Assert-Test ($parsed.ExitCode -eq 0)
    $script:Delays = @()
    function Start-Sleep { param([int]$Milliseconds) $script:Delays += $Milliseconds }
    $outbox = Join-Path $env:TEST_TMP 'outbox.txt'
    foreach ($pace in @(0, 800, 1500)) {
        $script:Delays = @()
        Write-AircOutbox -Outbox $outbox -Lines @(
            "PRIVMSG tm_console :PUT id=$id path=x",
            "PRIVMSG tm_console :CHUNK id=$id seq=1 data=YQ==",
            "PRIVMSG tm_console :PUTEND id=$id seqs=1"
        ) -PaceMs $pace
        Assert-Test ($script:Delays.Count -eq 2)
        Assert-Test ($script:Delays[0] -eq [Math]::Max(1200, $pace) -and $script:Delays[1] -eq [Math]::Max(1200, $pace))
    }
    $script:Delays = @()
    Write-AircOutbox -Outbox $outbox -Lines @('PRIVMSG tm_console :STATUS', 'PRIVMSG tm_console :VERSION') -PaceMs 800
    Assert-Test ($script:Delays.Count -eq 1 -and $script:Delays[0] -eq 800)
    Write-Output 'FR5838 PASSED'
    """
    env = dict(os.environ, TEST_SCRIPT=str(SCRIPT), TEST_TMP=str(tmp_path))
    result = subprocess.run(
        [PS, "-NoProfile", "-Command", command], env=env,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FR5838 PASSED" in result.stdout
