"""FR #5059: !recycleseat <nick> [machine] — elevated tray stop+verify+start."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

import recycleseat as rs
import startworker as sw

NOW = 1_800_000_000.0
MID = lambda n: (n[4:].lower() if str(n).lower().startswith("bob-") else None)  # noqa: E731


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("BOB_RECYCLESEAT_DISABLE", "BOB_OP_ACCOUNTS", "BOB_STARTWORKER_DISABLE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("JEEVES_OWNER_ACCOUNT", "simon")


@pytest.fixture
def root(tmp_path):
    install = tmp_path / "bob"
    install.mkdir()
    adir = sw.queue_dir(install)
    adir.mkdir(parents=True)
    (adir / sw.ALIVE_FILE).write_text("alive")
    os.utime(adir / sw.ALIVE_FILE, (NOW, NOW))
    (adir / sw.ENGINE_ALIVE_FILE).write_text("engine")
    os.utime(adir / sw.ENGINE_ALIVE_FILE, (NOW, NOW))
    q = rs.queue_dir(install)
    q.mkdir(parents=True)
    return install, q


def _ops(channel="#marchhare", nick="Simon"):
    """member_lookup: nick has +o in channel."""

    def lookup(ch, n):
        if ch.lower().lstrip("#") == channel.lower().lstrip("#") and n.lower() == nick.lower():
            return {"o"}
        return set()

    return lookup


def ask(
    root_q,
    body="!recycleseat marchhare-6700",
    nick="Simon",
    account="simon",
    channel="#marchhare",
    local="marchhare",
    member_lookup=None,
    now=NOW,
    home=None,
):
    install, q = root_q
    return rs.decide(
        body=body,
        nick=nick,
        account=account,
        channel=channel,
        local_machine=local,
        qdir=q,
        install_root=install,
        home=home,
        machine_of_nick=MID,
        member_lookup=member_lookup or _ops(channel, nick),
        now=now,
    )


@pytest.mark.parametrize(
    "body,want",
    [
        ("!recycleseat marchhare-6700", ("marchhare-6700", None)),
        ("!recycleseat flamingo-1 flamingo", ("flamingo-1", "flamingo")),
        (":!RecycleSeat marchhare-99 #marchhare", ("marchhare-99", "marchhare")),
        ("!recycleseat", "usage"),
        ("!recycleseat a b c", "usage"),
        ("!recycleseats x", None),
        ("hello", None),
    ],
)
def test_fr5059_syntax(body, want):
    assert rs.parse(body) == want


@pytest.mark.parametrize(
    "nick,acct,modes,ok,kind",
    [
        ("Simon", "simon", {"o"}, True, "op"),
        ("Simon", "simon", {"h"}, True, "op"),
        ("Simon", None, {"o"}, True, "op"),  # FR #5756: live +o without NickServ account
        ("mallory", "mallory", set(), False, ""),
        ("Bob-marchhare", "bob-marchhare", set(), True, "ear"),
        ("Bob-marchhare", "mallory", set(), False, ""),
        ("Jeeves", "jeeves", set(), True, "chair"),
        ("Jeeves", None, set(), True, "chair"),  # FR #5756: chair nick without account
        ("whoever", "simon", set(), True, "owner"),  # verified owner without MODE
    ],
)
def test_fr5059_authorize_op_or_ear(nick, acct, modes, ok, kind):
    lookup = lambda ch, n: modes if n.lower() == nick.lower() else set()  # noqa: E731
    got_ok, got_kind, _ = rs.authorize(
        nick, acct, channel="#marchhare", machine_of_nick=MID, member_lookup=lookup
    )
    assert (got_ok, got_kind) == (ok, kind if ok else "")


def test_fr5059_op_acked_and_request_queued(root):
    d = ask(root)
    assert d.ok and d.line.startswith("ACK recycleseat marchhare-6700 on marchhare")
    _, q = root
    files = list(q.glob("req-*.json"))
    assert len(files) == 1
    req = json.loads(files[0].read_text(encoding="utf-8"))
    assert req["nick"] == "marchhare-6700"
    assert req["by"] == "Simon" and req["kind"] == "op"
    assert set(req) == {"id", "nick", "by", "kind", "ts", "expires"}


def test_fr5059_bobiverse_needs_machine(root):
    d = ask(root, channel="#bobiverse")
    assert not d.ok and d.reason == "machine_required"
    d = ask(root, "!recycleseat marchhare-6700 marchhare", channel="#bobiverse")
    assert d.ok


def test_fr5059_other_machine_silent(root):
    assert ask(root, "!recycleseat x flamingo", channel="#bobiverse") is None


def test_fr5059_denied_and_unverified_queue_nothing(root):
    # FR #5756: +o without account is allowed; unverified is no-account + no op + not chair.
    d = ask(root, account=None, member_lookup=lambda ch, n: set())
    assert not d.ok and d.reason == "unverified"
    d = ask(
        root,
        nick="mallory",
        account="mallory",
        member_lookup=lambda ch, n: set(),
    )
    assert not d.ok and d.reason == "denied"
    _, q = root
    assert not list(q.glob("req-*.json"))


def test_fr5059_no_tray_alive_nacks(root):
    install, q = root
    adir = sw.queue_dir(install)
    (adir / sw.ALIVE_FILE).unlink()
    d = ask(root)
    assert not d.ok and d.reason == "no_interactive_session"
    assert not list(q.glob("req-*.json"))


@pytest.mark.parametrize(
    "stop_ok,alive,found,may,reason",
    [
        (True, False, True, True, "ok"),
        (False, True, True, False, "stop-failed"),
        (True, True, True, False, "still-alive"),
        (True, False, False, False, "not-found"),
        (True, False, True, False, "expired"),  # overridden below
    ],
)
def test_fr5059_plan_never_starts_unless_stop_verified(stop_ok, alive, found, may, reason):
    if reason == "expired":
        assert rs.plan_recycle_action(
            stop_ok=True, target_still_alive=False, target_found=True, expired=True
        ) == (False, "expired")
        return
    assert rs.plan_recycle_action(
        stop_ok=stop_ok, target_still_alive=alive, target_found=found
    ) == (may, reason)


def test_fr5059_tray_ps1_stop_before_start_and_intake():
    """Hostile contract: tray helper stops+verifies before launch; failures report."""
    root = Path(__file__).resolve().parents[2]
    ps1 = root / "bob" / "tray" / "tools" / "BobTrayRecycleSeat.ps1"
    assert ps1.is_file(), "BobTrayRecycleSeat.ps1 must exist"
    t = ps1.read_text(encoding="utf-8-sig")
    assert "FR #5059" in t
    assert "Stop-BobWorkerSeatTrees" in t or "Stop-Process" in t
    assert "still-alive" in t or "still_alive" in t or "still alive" in t.lower()
    assert "not-found" in t or "not_found" in t
    # never start when stop failed
    assert "may_start" in t.lower() or "plan_recycle" in t.lower() or (
        "stop" in t.lower() and "Start-BobTrayWorkerExe" in t
    )
    assert "Report-BobRuntimeFailure" in t or "Invoke-BobMustReportFailure" in t
    assert "Write-TrayLog" in t or "recycleseat" in t.lower()


def test_mrb5060_recycle_failure_loads_helpers_from_install_root():
    """Hostile: live Watch -RepoRoot is the install root, not bob\\tray."""
    root = Path(__file__).resolve().parents[2]
    t = (root / "bob" / "tray" / "tools" / "BobTrayRecycleSeat.ps1").read_text(
        encoding="utf-8-sig"
    )
    assert "tray\\src\\Private\\Invoke-BobMustReportFailure.ps1" in t
    assert "common\\scripts\\Report-BobRuntimeFailure.ps1" in t


def test_fr5059_watch_consumes_recycleseat_queue():
    root = Path(__file__).resolve().parents[2]
    watch = (root / "bob" / "tray" / "tools" / "Watch-BobTray.ps1").read_text(
        encoding="utf-8-sig"
    )
    assert "BobTrayRecycleSeat" in watch or "Invoke-BobTrayRecycleSeatQueue" in watch


def test_fr5059_irc_agent_wires_command():
    root = Path(__file__).resolve().parents[2]
    src = (root / "common" / "scripts" / "irc_agent.py").read_text(encoding="utf-8")
    assert "recycleseat" in src
    assert "_maybe_recycleseat" in src


def test_fr5084_vendor_sync_owned_tools_keeps_recycleseat():
    """Vendor re-sync wipes OutDir; RecycleSeat must be in $ownedTools (FR #5084)."""
    root = Path(__file__).resolve().parents[2]
    sync = (root / "bob" / "scripts" / "Sync-BobTrayFromAgenticBuild.ps1").read_text(
        encoding="utf-8-sig"
    )
    start = sync.index("$ownedTools = @(")
    end = sync.index(")", start)
    block = sync[start : end + 1]
    assert "BobTrayStartWorker.ps1" in block
    assert "BobTrayRecycleSeat.ps1" in block
