"""Remote worker start over IRC (t810u): ``!startworker [agent|plan] [machine]``.
Ear = authorise + cap + cooldown + queue (pure, startworker.py); tray = launch via the Agent-click function."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import irc_agent
import startworker as sw
from repo_layout import REPO, ROOT

TRAY_TOOLS = ROOT / "third_party" / "bob-tray" / "tools"
WIN = pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell"), reason="needs Windows PowerShell")
NOW = 1_800_000_000.0
MID = lambda n: (n[4:].lower() if str(n).lower().startswith("bob-") else None)   # noqa: E731


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("BOB_STARTWORKER_MAX", "BOB_STARTWORKER_COOLDOWN_S", "BOB_STARTWORKER_DISABLE", "BOB_OP_ACCOUNTS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("JEEVES_OWNER_ACCOUNT", "simon")


@pytest.fixture
def q(tmp_path):
    d = sw.queue_dir(tmp_path / "bob")
    d.mkdir(parents=True)
    (d / sw.ALIVE_FILE).write_text("alive")
    os.utime(d / sw.ALIVE_FILE, (NOW, NOW))
    return d


def ask(q, body="!startworker", nick="Simon", account="simon", channel="#marchhare", gate=None, procs=lambda: [], now=NOW,
        home=None, local="marchhare"):
    return sw.decide(body=body, nick=nick, account=account, channel=channel, local_machine=local,
                     gate=gate or sw.StartGate(max_workers=4, cooldown_s=30), qdir=q, home=home, machine_of_nick=MID,
                     procs=procs, now=now)


# ------------------------------------------------------------------------------------------------ syntax
@pytest.mark.parametrize("body,want", [
    ("!startworker", ("agent", None)), ("!startworker agent", ("agent", None)), ("!StartWorker PLAN", ("plan", None)),
    ("!startworker marchhare", ("agent", "marchhare")), ("!startworker plan marchhare", ("plan", "marchhare")),
    ("!startworker marchhare plan", ("plan", "marchhare")), (":!startworker agent #marchhare", ("agent", "marchhare")),
    ("!startworker a b c", "usage"), ("!startworker agent plan", "usage"), ("!startworker rm -rf /", "usage"),
    ("!startworkers", None), ("hello !startworker", None), ("", None),
])
def test_syntax(body, want):
    assert sw.parse(body) == want


# ------------------------------------------------------------------------------------------------ who may ask
@pytest.mark.parametrize("nick,acct,ok,kind,why", [
    ("Simon", "simon", True, "owner", ""), ("whoever", "simon", True, "owner", ""),             # owner = account, any nick
    ("Simon", None, False, "", "unverified"), ("simon", "", False, "", "unverified"),           # nick alone proves nothing
    ("Jeeves", "jeeves", True, "chair", ""), ("Jeeves", "mallory", False, "", "denied"),
    ("Bob-win-mpre8vi4u6u", "bob-win-mpre8vi4u6u", True, "ear", ""),
    ("bob-flamingo_", "bob-flamingo", True, "ear", ""),
    ("Bob-flamingo", "mallory", False, "", "denied"),                                           # look-alike under another account
    ("mallory", "mallory", False, "", "denied"), ("marchhare-3556", "marchhare-3556", False, "", "denied"),  # a worker seat is not an operator
])
def test_authorize(nick, acct, ok, kind, why):
    assert sw.authorize(nick, acct, machine_of_nick=MID) == (ok, kind, why)


def test_extra_owner_accounts_from_env(monkeypatch):
    monkeypatch.setenv("BOB_OP_ACCOUNTS", "alice, Bob2")
    assert sw.authorize("x", "alice", machine_of_nick=MID)[1] == "owner"


# ------------------------------------------------------------------------------------------------ decisions
def test_owner_in_the_machine_channel_is_acked_and_the_request_is_queued(q):
    d = ask(q)
    assert d.ok and d.line.startswith("ACK startworker agent on marchhare") and "workers 1/2" in d.line
    f = list(q.glob("req-*.json"))
    assert len(f) == 1
    req = json.loads(f[0].read_text())
    assert req["mode"] == "agent" and req["by"] == "Simon" and req["kind"] == "owner" and req["expires"] == req["ts"] + 60
    assert set(req) == {"id", "mode", "by", "kind", "ts", "expires"}                # nothing else crosses: no secrets


def test_plan_mode_and_the_bobiverse_channel_needs_the_machine_name(q):
    assert ask(q, "!startworker plan").mode == "plan"
    d = ask(q, "!startworker agent", channel="#bobiverse", gate=sw.StartGate(4, 0))
    assert not d.ok and d.reason == "machine_required" and d.line.startswith("NACK startworker:")
    d = ask(q, "!startworker agent marchhare", channel="#bobiverse", gate=sw.StartGate(4, 0))
    assert d.ok


def test_other_machines_ear_stays_silent(q):
    assert ask(q, "!startworker agent flamingo", channel="#bobiverse") is None
    assert ask(q, "hello") is None
    assert not list(q.glob("req-*.json"))


def test_unverified_and_denied_get_a_nack_and_queue_nothing(q):
    d = ask(q, account=None)
    assert not d.ok and d.reason == "unverified" and "not verified" in d.line
    d = ask(q, nick="mallory", account="mallory")
    assert not d.ok and d.reason == "denied"
    assert not list(q.glob("req-*.json"))


def test_nobody_logged_in_no_tray_heartbeat_is_a_nack_with_the_reason(q, tmp_path):
    (q / sw.ALIVE_FILE).unlink()
    d = ask(q)
    assert not d.ok and d.reason == "no_interactive_session" and "nobody is logged in" in d.line
    (q / sw.ALIVE_FILE).write_text("x")
    os.utime(q / sw.ALIVE_FILE, (NOW - 120, NOW - 120))          # tray died / user logged off: stale
    assert ask(q).reason == "no_interactive_session"
    assert ask(sw.queue_dir(tmp_path / "never-installed")).reason == "no_interactive_session"
    assert not list(q.glob("req-*.json"))


def test_hard_cap_is_two_seats_counted_from_live_processes_not_the_onefile_bootloader_children(q):
    one = [(10, 1, "bob-worker-aaa.exe"), (11, 10, "bob-worker-aaa.exe"), (99, 1, "grok.exe"), (98, 11, "python.exe")]   # ONE seat
    two = one + [(20, 1, "bob-worker-aaa.exe"), (21, 20, "bob-worker-aaa.exe")]                                       # TWO seats
    three = two + [(30, 1, "bob-worker.exe")]
    assert (sw.count_workers([]), sw.count_workers(one), sw.count_workers(two), sw.count_workers(three)) == (0, 1, 2, 3)
    d = ask(q, gate=sw.StartGate(max_workers=9, cooldown_s=0), procs=lambda: two)           # env/gate can never raise the cap above 2
    assert not d.ok and d.reason == "cap" and d.line == "NACK startworker: max 2 workers (2 running on marchhare)"
    assert ask(q, gate=sw.StartGate(max_workers=9, cooldown_s=0), procs=lambda: three).reason == "cap"
    assert ask(q, gate=sw.StartGate(max_workers=9, cooldown_s=0), procs=lambda: one).ok      # 1 running -> the 2nd is allowed
    assert len(list(q.glob("req-*.json"))) == 1                                              # refusals queue nothing


def test_the_gate_can_lower_the_cap_but_never_raise_it(q):
    one = [(10, 1, "bob-worker.exe")]
    d = ask(q, gate=sw.StartGate(max_workers=1, cooldown_s=0), procs=lambda: one)
    assert not d.ok and "max 1 workers" in d.line


def test_cooldown_blocks_a_second_start_until_it_passes(q):
    g = sw.StartGate(max_workers=9, cooldown_s=30)
    assert ask(q, gate=g, now=NOW).ok
    d = ask(q, gate=g, now=NOW + 10)
    assert not d.ok and d.reason == "cooldown" and "20s" in d.line
    os.utime(q / sw.ALIVE_FILE, (NOW + 30, NOW + 30))                # tray heartbeat keeps ticking
    assert ask(q, gate=g, now=NOW + 31).ok
    assert len(list(q.glob("req-*.json"))) == 2


def test_a_nack_does_not_start_the_cooldown(q):
    g = sw.StartGate(max_workers=9, cooldown_s=30)
    assert not ask(q, account=None, gate=g).ok
    assert ask(q, gate=g).ok


def test_kill_switch_file_and_env(q, tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    assert ask(q, home=home).ok
    (home / sw.DISABLE_FILE).write_text("")
    d = ask(q, home=home, gate=sw.StartGate(4, 0))
    assert not d.ok and d.reason == "disabled"
    (home / sw.DISABLE_FILE).unlink()
    monkeypatch.setenv("BOB_STARTWORKER_DISABLE", "1")
    assert ask(q, home=home, gate=sw.StartGate(4, 0)).reason == "disabled"


def test_defaults_and_env_overrides(monkeypatch):
    g = sw.StartGate()
    assert (g.max_workers, g.cooldown_s, sw.HARD_MAX_WORKERS) == (2, 30.0, 2)
    monkeypatch.setenv("BOB_STARTWORKER_MAX", "7")
    monkeypatch.setenv("BOB_STARTWORKER_COOLDOWN_S", "5")
    g = sw.StartGate()
    assert (g.max_workers, g.cooldown_s) == (2, 5.0)          # 7 is clamped to the hard cap of 2
    monkeypatch.setenv("BOB_STARTWORKER_MAX", "1")
    assert sw.StartGate().max_workers == 1


def test_snapshot_procs_runs_and_never_raises():
    rows = sw.snapshot_procs()
    assert isinstance(rows, list)
    if sys.platform == "win32":
        assert any(pid == os.getpid() for pid, _pp, _n in rows)


# ------------------------------------------------------------------------------------------------ the ear glue (real Client method)
class FakeBob:
    def __init__(self, tmp_path):
        self.args = SimpleNamespace(chair=False)
        self.home = tmp_path / "home"
        self.home.mkdir()
        self.live_nick = self.original_nick = "Bob-marchhare"
        self.sent, self.pms, self.whois = [], [], []
        self.acct = {}
        self.root = tmp_path / "root"

    def send_privmsg_lines(self, line): self.sent.append(line); return [line]
    def whisper(self, nick, msg): self.pms.append((nick, msg))
    def _mine_nicks(self): return {"bob-marchhare"}
    def _local_machine_id(self): return "marchhare"
    def _account_of(self, n): return self.acct.get(n.lower())
    def _whois_hint(self, n): self.whois.append(n)
    def _install_root(self): return self.root

    _maybe_startworker = irc_agent.Client._maybe_startworker


@pytest.fixture
def bob(tmp_path, monkeypatch):
    b = FakeBob(tmp_path)
    d = sw.queue_dir(b.root)
    d.mkdir(parents=True)
    (d / sw.ALIVE_FILE).write_text("alive")
    monkeypatch.setattr(irc_agent.time, "sleep", lambda s: None)
    monkeypatch.setattr(irc_agent, "info", lambda m: None)
    monkeypatch.setattr(sw, "snapshot_procs", lambda: [])
    monkeypatch.setattr(sw, "decide", sw.decide)
    b.qdir = d
    return b


def test_ear_acks_on_the_channel_it_was_asked_in_and_queues(bob):
    bob.acct["simon"] = "simon"
    assert bob._maybe_startworker("Simon", "#marchhare", "!startworker plan", to_channel=True, to_me=False)
    assert len(bob.sent) == 1 and bob.sent[0].startswith("PRIVMSG #marchhare :ACK startworker plan on marchhare")
    assert len(list(bob.qdir.glob("req-*.json"))) == 1


def test_ear_nacks_unverified_and_asks_whois(bob):
    assert bob._maybe_startworker("Simon", "#marchhare", "!startworker", to_channel=True, to_me=False)
    assert bob.sent and "NACK startworker: not verified" in bob.sent[0]
    assert bob.whois == ["Simon"] and not list(bob.qdir.glob("req-*.json"))


def test_ear_bob_peer_in_bobiverse_names_the_machine(bob):
    bob.acct["bob-win-x"] = "bob-win-x"
    assert bob._maybe_startworker("Bob-win-x", "#bobiverse", "!startworker agent marchhare", to_channel=True, to_me=False)
    assert bob.sent[0].startswith("PRIVMSG #bobiverse :ACK startworker agent on marchhare")
    bob.sent.clear()
    assert bob._maybe_startworker("Bob-win-x", "#bobiverse", "!startworker agent flamingo", to_channel=True, to_me=False)
    assert bob.sent == []                                            # someone else's machine: silent


def test_ear_pm_gets_a_pm_reply_and_ignores_itself_and_chair_ears(bob, tmp_path):
    bob.acct["simon"] = "simon"
    assert bob._maybe_startworker("Simon", "Bob-marchhare", "!startworker marchhare", to_channel=False, to_me=True)
    assert bob.pms and bob.pms[0][1].startswith("ACK startworker") and bob.sent == []
    assert bob._maybe_startworker("Bob-marchhare", "#marchhare", "!startworker", to_channel=True, to_me=False) is True
    assert len(bob.pms) == 1                                         # our own echo is never answered
    bob.args = SimpleNamespace(chair=True)
    assert bob._maybe_startworker("Simon", "#marchhare", "!startworker", to_channel=True, to_me=False) is False   # Jeeves has no host ops
    bob.args = SimpleNamespace(chair=False)
    assert bob._maybe_startworker("Simon", "#marchhare", "hello", to_channel=True, to_me=False) is False


def test_dispatch_runs_before_the_other_command_handlers():
    src = (REPO / "common" / "scripts" / "irc_agent.py").read_text(encoding="utf-8")
    assert src.index("self._maybe_startworker(src, target, body") < src.index("bobtalk.parse_recycle_command(body)")
    assert "import startworker" in src


# ------------------------------------------------------------------------------------------------ the tray side (real PowerShell)
def _ps(tmp_path, body, timeout=90):
    f = tmp_path / "t.ps1"
    f.write_text(body, encoding="utf-8-sig")
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(f)],
                       capture_output=True, text=True, timeout=timeout)
    return r.stdout + r.stderr


@WIN
def test_tray_consumes_a_python_written_request_once_and_launches_via_the_click_function(tmp_path):
    qd = tmp_path / "root" / "run" / "startworker"
    rid = sw.write_request(qd, "plan", "Simon", "owner")
    out = _ps(tmp_path, r'''
. "%s"
$dir = Get-BobTrayStartWorkerDir -Root "%s"
$global:launched = New-Object System.Collections.Generic.List[string]
$r1 = @(Invoke-BobTrayStartWorkerQueue -Dir $dir -Launch { param($m) $global:launched.Add($m); 4242 })
$r2 = @(Invoke-BobTrayStartWorkerQueue -Dir $dir -Launch { param($m) $global:launched.Add($m); 4243 })
"R1=" + ($r1 | ForEach-Object { '{0}|{1}|{2}|{3}' -f $_.ok, $_.mode, $_.pid, $_.reason })
"R2=" + $r2.Count
"LAUNCHED=" + ($global:launched -join ',')
"REQLEFT=" + @(Get-ChildItem $dir -Filter 'req-*.json').Count
"ALIVE=" + (Test-Path (Join-Path $dir 'tray.alive'))
"RES=" + (Get-Content (Join-Path $dir 'res-%s.json') -Raw)
''' % (TRAY_TOOLS / "BobTrayStartWorker.ps1", tmp_path / "root", rid))
    assert "R1=True|plan|4242|" in out and "R2=0" in out and "LAUNCHED=plan" in out      # at-most-once
    assert "REQLEFT=0" in out and "ALIVE=True" in out
    assert '"ok":true' in out and '"pid":4242' in out
    assert sw.tray_alive(qd)                                                              # the ear sees the heartbeat


@WIN
def test_tray_drops_expired_bad_mode_unreadable_and_a_launch_that_throws_is_never_replayed(tmp_path):
    qd = tmp_path / "root" / "run" / "startworker"
    qd.mkdir(parents=True)
    past = int(time.time()) - 600
    (qd / "req-old.json").write_text(json.dumps({"id": "old", "mode": "agent", "by": "x", "kind": "owner", "ts": past, "expires": past + 60}))
    fut = int(time.time()) + 600
    (qd / "req-evil.json").write_text(json.dumps({"id": "evil", "mode": "agent; calc", "by": "x", "kind": "owner", "ts": 1, "expires": fut}))
    (qd / "req-junk.json").write_text("{not json")
    (qd / "req-boom.json").write_text(json.dumps({"id": "boom", "mode": "agent", "by": "x", "kind": "owner", "ts": 1, "expires": fut}))
    # FR #2667: CapRefusal reads live bob-worker seats; stub empty so boom reaches Launch throw
    # (this test is about expired/bad-mode/unreadable/launch-error, not the agent-only cap).
    out = _ps(tmp_path, r'''
. "%s"
function Get-BobTrayWorkerCapRefusal { param([object[]]$Procs = $null, [string]$Mode = 'agent') '' }
$dir = Get-BobTrayStartWorkerDir -Root "%s"
$global:n = 0
$r = @(Invoke-BobTrayStartWorkerQueue -Dir $dir -Launch { param($m) $global:n++; throw 'nope' })
"LAUNCH_CALLS=" + $global:n
$r | ForEach-Object { 'ROW=' + $_.id + '|' + $_.ok + '|' + $_.reason }
"REQLEFT=" + @(Get-ChildItem $dir -Filter 'req-*.json').Count
$r2 = @(Invoke-BobTrayStartWorkerQueue -Dir $dir -Launch { param($m) $global:n++; 1 })
"AGAIN=" + $r2.Count + " CALLS=" + $global:n
''' % (TRAY_TOOLS / "BobTrayStartWorker.ps1", tmp_path / "root"))
    assert "LAUNCH_CALLS=1" in out                       # only the valid-looking one reached the launcher
    assert "ROW=old|False|expired" in out and "ROW=evil|False|bad-mode" in out and "ROW=junk|False|unreadable" in out
    assert "ROW=boom|False|launch-error: nope" in out
    assert "REQLEFT=0" in out and "AGAIN=0 CALLS=1" in out


def test_tray_wiring_timer_heartbeat_helper_and_click_function_contract():
    w = (TRAY_TOOLS / "Watch-BobTray.ps1").read_text(encoding="utf-8")
    assert "'BobTrayStartWorker.ps1'" in w
    assert "Invoke-BobTrayStartWorkerQueue -Dir $script:startWorkerDir" in w
    assert "Start-BobTrayWorkerExe -Mode $mode -Quiet" in w                    # the SAME function as the Agent / Plan click
    assert "$startWorkerTimer.Start()" in w and "$startWorkerTimer.Stop()" in w
    assert "Write-BobTrayAlive" in w and "'tray.alive'" in w                   # heartbeat removed on exit => ear NACKs at once
    i = w.index("function Start-BobTrayWorkerExe")
    body = w[i:w.index("$script:attention = $false", i)]
    assert "[switch]$Quiet" in body and "return [int]$childPid" in body and "-not $Quiet" in body
    assert "Start-BobTrayWorkerExe -Mode 'agent' })" in w                      # the click still works unchanged
    sync = (ROOT / "scripts" / "Sync-BobTrayFromAgenticBuild.ps1").read_text(encoding="utf-8")
    assert "BobTrayStartWorker.ps1" in sync                                    # survives a vendor re-sync


@WIN
def test_tray_cap_refuses_a_third_live_worker_and_ignores_stale_state(tmp_path):
    out = _ps(tmp_path, r'''
. "%s"
function P($id, $pp, $n) { [pscustomobject]@{ ProcessId = $id; ParentProcessId = $pp; Name = $n } }
$one = @((P 10 1 'bob-worker-aaa.exe'), (P 11 10 'bob-worker-aaa.exe'), (P 50 1 'grok.exe'))
$two = $one + @((P 20 1 'bob-worker-aaa.exe'), (P 21 20 'bob-worker-aaa.exe'))
$three = $two + @((P 30 1 'bob-worker.exe'))
"SEATS=" + (Measure-BobTrayWorkerSeats -Procs @()) + "," + (Measure-BobTrayWorkerSeats -Procs $one) + "," + (Measure-BobTrayWorkerSeats -Procs $two) + "," + (Measure-BobTrayWorkerSeats -Procs $three)
"ONE=[" + (Get-BobTrayWorkerCapRefusal -Procs $one) + "]"
"TWO=[" + (Get-BobTrayWorkerCapRefusal -Procs $two) + "]"
"THREE=[" + (Get-BobTrayWorkerCapRefusal -Procs $three) + "]"
''' % (TRAY_TOOLS / "BobTrayStartWorker.ps1"))
    assert "SEATS=0,1,2,3" in out and "ONE=[]" in out
    assert "TWO=[Max 2 workers (2 already running). Close a worker window first.]" in out
    assert "THREE=[Max 2 workers (3 already running)" in out


def test_tray_launch_checks_the_cap_first_with_a_short_message_and_the_remote_path_stays_quiet():
    w = (TRAY_TOOLS / "Watch-BobTray.ps1").read_text(encoding="utf-8")
    i = w.index("function Start-BobTrayWorkerExe")
    body = w[i:w.index("$script:attention = $false", i)]
    assert body.index("Get-BobTrayWorkerCapRefusal") < body.index("Get-FileHash")                 # before anything is copied or started
    assert "if (-not $Quiet) { try { [void][System.Windows.Forms.MessageBox]::Show($capRefusal" in body
    assert "return 0" in body[body.index("Get-BobTrayWorkerCapRefusal"):body.index("Get-FileHash")]
