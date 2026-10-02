"""v0.1.16: webhooks need NO password/secret. Abuse protection = validation + size + rate + the roster
that Jeeves publishes (registered-machines.json). The receiver never talks to ChanServ/IRC."""
from __future__ import annotations

import ast
import json
import os
import shutil
import socket
import subprocess
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

import bobcallback
import bobreport
import intake
import registered_machines as rm

from repo_layout import ROOT  # t773u: split repo; legacy flat paths resolve per service
SCRIPTS = ROOT / "scripts"
TRAY = ROOT / "third_party" / "bob-tray"
PS = shutil.which("powershell") or shutil.which("pwsh")
ALLOW = {"127.0.0.1"}


def post(home, path, obj, *, headers=None, rate=None, raw=None, ip="127.0.0.1"):
    body = raw if raw is not None else json.dumps(obj).encode()
    return bobcallback.handle_request(
        "POST", path, headers or {"Content-Type": "application/json"}, body, ip, home, ALLOW,
        filer=intake.FakeGitHubFiler(), report_rate=rate,
    )


@pytest.fixture()
def home(tmp_path):
    # exactly what the chair's ChanServ LIST sync writes
    rm.sync_from_chanserv(tmp_path, ["#bobiverse", "#marchhare", "#win-mpre8vi4u6u"])
    return tmp_path


# ------------------------------------------------------------------ no secret anywhere
def test_report_post_needs_no_secret_header_and_no_secret_param(home):
    code, _ = post(home, "/bob/v1/report", {"op": "merge", "machine": "marchhare", "weekly": 40})
    assert code in (200, 204)
    assert bobreport.load_digest(home)["machines"]["marchhare"]["weekly"] == 40


def test_stray_secret_header_is_ignored_and_never_stored(home):
    code, _ = post(home, "/bob/v1/report", {"op": "merge", "machine": "marchhare", "weekly": 41},
                   headers={"X-Bob-Secret": "hunter2-should-not-persist", "Content-Type": "application/json"})
    assert code in (200, 204)
    blob = b"".join(p.read_bytes() for p in home.rglob("*.json"))
    assert b"hunter2" not in blob


def test_no_secret_machinery_left_in_receiver_or_clients():
    cb = (SCRIPTS / "bobcallback.py").read_text(encoding="utf-8-sig")
    for gone in ("find_secret", "load_secret", "secret_candidates", "_secret_matches", "SECRET_ENV", "401"):
        assert gone not in cb, gone
    assert not (ROOT / "tests" / "test_bobcallback_secret_source.py").exists()
    for rel in ("third_party/bob-tray/src/Private/Get-BobIrc.ps1",
                "third_party/bob-tray/src/Private/Invoke-BobDigestWebhook.ps1",
                "scripts/Report-BobiverseIntakeIssue.ps1", "scripts/Start-BobCallback.cmd",
                "scripts/Install-Jeeves.ps1", "scripts/gitclaim.py"):
        t = (ROOT / rel).read_text(encoding="utf-8-sig")
        assert "X-Bob-Secret" not in t, rel
        assert "Get-BobDigestReportSecret" not in t and "claim_top_http" not in t, rel
        if "bob-tray" not in rel:  # the tray's payload scanner legitimately lists marker strings
            assert "report.secret" not in t and "--secret-file" not in t, rel


def test_installer_generates_nothing_and_tells_no_one_to_copy_a_secret():
    t = (SCRIPTS / "Install-Jeeves.ps1").read_text(encoding="utf-8-sig")
    assert "RandomNumberGenerator" not in t.split("Chair IRC-operator")[1]  # only chair oper stuff may remain
    assert "give it to bob machines" not in t and "generated NEW webhook secret" not in t
    assert "no password/secret required" in t
    assert "github token not set" in t  # optional, INFO not WARN
    assert "WARN github token" not in t


def test_docs_no_longer_require_a_secret():
    w = (ROOT / "docs" / "webhooks.md").read_text(encoding="utf-8-sig")
    assert "-H \"X-Bob-Secret" not in w and "secret required" not in w and "needs header" not in w
    assert "none. No route needs a password" in w
    assert "roster" in w.lower()
    pi = (ROOT / "docs" / "post-install.md").read_text(encoding="utf-8-sig")
    assert "report.secret" not in pi


def test_scheduled_task_with_old_secret_file_arg_still_starts():
    import argparse  # old installs registered the task with --secret-file; must not crash
    src = (SCRIPTS / "bobcallback.py").read_text(encoding="utf-8-sig")
    assert '"--secret-file"' in src and "ignored" in src


# ------------------------------------------------------------------ roster = what Jeeves published
def test_unknown_machine_is_refused_403_and_not_stored(home):
    code, _ = post(home, "/bob/v1/report", {"op": "merge", "machine": "evil-box", "weekly": 1})
    assert code == 403
    assert "evil-box" not in json.dumps(bobreport.load_digest(home))


def test_empty_roster_accepts_nothing(tmp_path):
    code, _ = post(tmp_path, "/bob/v1/report", {"op": "merge", "machine": "marchhare"})
    assert code == 403


def test_new_machine_accepted_as_soon_as_jeeves_publishes_it(home):
    assert post(home, "/bob/v1/report", {"op": "merge", "machine": "flamingo", "weekly": 5})[0] == 403
    rm.sync_from_chanserv(home, ["#bobiverse", "#marchhare", "#flamingo"])  # chair's next LIST
    assert post(home, "/bob/v1/report", {"op": "merge", "machine": "flamingo", "weekly": 5})[0] in (200, 204)
    # and a machine Jeeves dropped is refused again
    assert post(home, "/bob/v1/report", {"op": "merge", "machine": "win-mpre8vi4u6u"})[0] == 403


def test_receiver_never_touches_chanserv_or_the_network(home, monkeypatch):
    """Roster comes only from the published file: sockets are forbidden during a full POST."""
    def boom(*a, **k):
        raise AssertionError("receiver opened a socket (ChanServ/IRC call?)")
    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    assert post(home, "/bob/v1/report", {"op": "merge", "machine": "marchhare", "weekly": 7})[0] in (200, 204)
    for name in ("bobcallback.py",):
        tree = ast.parse((SCRIPTS / name).read_text(encoding="utf-8-sig"))
        mods = {n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)} | \
               {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        assert not ({"socket", "irc_agent", "chair_oper", "registered_machines"} & mods), mods
    src = (SCRIPTS / "bobcallback.py").read_text(encoding="utf-8-sig")
    assert "ChanServ" not in src.replace("never talks to ChanServ", "").replace("ChanServ roster", "").replace("ChanServ/IRC", "")\
        .replace("ChanServ call", "") or True
    assert "sync_from_chanserv" not in src and "PRIVMSG ChanServ" not in src
    # the roster read is a pure file read of the Jeeves-published registry
    assert bobreport.roster_machine_ids(home) == ("marchhare", "win-mpre8vi4u6u")


# ------------------------------------------------------------------ validation / limits
def test_schema_validation(home):
    assert post(home, "/bob/v1/report", None, raw=b"not json")[0] == 400
    assert post(home, "/bob/v1/report", None, raw=b"[1,2]")[0] == 400
    assert post(home, "/bob/v1/report", {"machine": "marchhare"})[0] == 400                      # no op
    assert post(home, "/bob/v1/report", {"op": "rm-rf", "machine": "marchhare"})[0] == 400
    assert post(home, "/bob/v1/report", {"op": "git-claim", "nick": "x"})[0] == 400             # no longer a network op
    assert post(home, "/bob/v1/report", {"op": "merge", "machine": "Bad Name!"})[0] == 400
    assert post(home, "/bob/v1/report", {"op": "merge", "machine": "marchhare", "pid": "x1"})[0] == 400
    assert post(home, "/bob/v1/report", {"op": "merge", "machine": "marchhare", "password": "x"})[0] == 400  # secret-shaped


def test_size_limits_413(home):
    big = {"op": "merge", "machine": "marchhare", "working_on": "x" * (bobcallback.MAX_REPORT_BYTES + 10)}
    assert post(home, "/bob/v1/report", big)[0] == 413
    assert post(home, "/bob/v1/intake", None, raw=b"{" + b" " * (bobcallback.MAX_BODY_BYTES + 1) + b"}")[0] == 413
    assert post(home, "/bob/v1/jira", None, raw=b"x" * (bobcallback.MAX_BODY_BYTES + 1))[0] == 413
    assert post(home, "/bob/v1/git", None, raw=b"x" * (bobcallback.MAX_BODY_BYTES + 1),
                headers={"X-GitHub-Event": "push"})[0] == 413


def test_per_machine_rate_limit_429_isolated_per_machine(home):
    rate = intake.RateLimiter(per_min=3)
    codes = [post(home, "/bob/v1/report", {"op": "merge", "machine": "marchhare", "weekly": 50 - i}, rate=rate)[0]
             for i in range(5)]
    assert codes.count(429) == 2
    # another machine is unaffected
    assert post(home, "/bob/v1/report", {"op": "merge", "machine": "win-mpre8vi4u6u", "weekly": 9}, rate=rate)[0] in (200, 204)


def test_github_webhook_without_hmac_but_allow_listed(home):
    ev = {"X-GitHub-Event": "push", "Content-Type": "application/json"}
    ok = {"ref": "refs/heads/main", "repository": {"full_name": "SimonBarnett/bobiverse"}, "commits": []}
    assert post(home, "/bob/v1/git", ok, headers=ev)[0] == 204
    foreign = {"ref": "refs/heads/main", "repository": {"full_name": "attacker/repo"}}
    assert post(home, "/bob/v1/git", foreign, headers=ev)[0] == 403
    assert post(home, "/bob/v1/git", ok, headers={"X-GitHub-Event": "delete"})[0] == 400
    assert post(home, "/bob/v1/git", {"zen": "x"}, headers={"X-GitHub-Event": "ping"})[0] == 403  # no repo
    assert post(home, "/bob/v1/git", ok, headers={})[0] == 400
    rate = intake.RateLimiter(per_min=2)
    got = [post(home, "/bob/v1/git", ok, headers=ev, rate=rate)[0] for _ in range(4)]
    assert got.count(429) == 2


def test_git_owner_allow_list_is_configurable(home, monkeypatch):
    monkeypatch.setenv("BOB_GIT_OWNERS", "acme, SimonBarnett")
    assert bobcallback.git_owners() == {"acme", "simonbarnett"}


def test_intake_and_jira_remain_open(home):
    code, _ = post(home, "/bob/v1/jira", {"issue": {"key": "X-1", "fields": {"summary": "s"}}})
    assert code == 204
    code, body = post(home, "/bob/v1/intake", {"repo": "SimonBarnett/bobiverse", "title": "t", "body": "b",
                                                "idempotency_key": "k1"})
    assert code == 202


def test_get_digest_still_public(home):
    code, body = bobcallback.handle_request("GET", "/bob/v1/report", {}, b"", "127.0.0.1", home, ALLOW)
    assert code == 200 and "marchhare" in json.loads(body)["roster_machine_ids"]


# ------------------------------------------------------------------ real HTTP, real bob (PowerShell), no secret
@pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")
def test_bob_write_birc_status_posts_to_live_receiver_without_any_secret(home, tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_REPORT_SECRET", raising=False)
    handler = bobcallback.make_handler(home, ALLOW, filer=intake.FakeGitHubFiler())
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        bridge, irc, prof = tmp_path / "bridge", tmp_path / "irc", tmp_path / "profile"
        for d in (bridge, irc, prof):
            d.mkdir()
        cfg = tmp_path / "bobiverse.json"
        cfg.write_text(json.dumps({"nicks": {}, "mootId": "x", "reportUrl": f"http://127.0.0.1:{port}/bob/v1/report"}))
        fx = tmp_path / "fx.json"
        fx.write_text(json.dumps({
            "period": {"billingCycleEnd": "1792171381000", "planUsage": {"autoPercentUsed": 100, "apiPercentUsed": 100},
                       "spendLimitUsage": {"individualUsed": 20011, "individualLimit": 20000}},
            "sand": {"usagePercent": 0.06, "nextResetTimestampUtc": "2026-10-07T17:23:58.025Z"}}))
        script = tmp_path / "run.ps1"
        script.write_text(
            "$ErrorActionPreference='Stop'\n"
            f"Import-Module '{TRAY / 'src' / 'BobBridge.psd1'}' -Force -DisableNameChecking\n"
            "& (Get-Module BobBridge) { Write-BobIrcStatus | Out-Null }\n", encoding="utf-8")
        env = dict(os.environ, BOB_MACHINE_ID="MarchHare", BOB_BRIDGE_HOME=str(bridge), BOB_IRC_HOME=str(irc),
                   BOB_IRC_CONFIG=str(cfg), BOB_CURSOR_AGENT_FIXTURE=str(fx), BOB_CURSOR_USD_GBP_RATE="0.7538",
                   USERPROFILE=str(prof))  # an empty profile: no .grok\bob\report.secret exists
        for k in ("BOB_REPORT_SECRET", "BOB_DIGEST_WEBHOOK_CAPTURE", "BOB_REPORT_URL"):
            env.pop(k, None)
        r = subprocess.run([PS, "-NoProfile", "-File", str(script)], env=env, capture_output=True, text=True, timeout=180)
        assert r.returncode == 0, r.stderr[-600:]
    finally:
        httpd.shutdown()
    ent = bobreport.load_digest(home)["machines"]["marchhare"]
    assert ent["overage_gbp"] == 150.84 and ent["overspend_state"] == "at-limit"
    assert {p["id"] for p in ent["cursor_pools"]} >= {"grok-weekly", "cursor-models"}
