"""FR #5890: never recycle a working seat or one recently ACKed."""
import json
import os
from types import SimpleNamespace

import pytest

import bobreport
import irc_agent
import recycleseat as rs
import startworker as sw

NOW = 1_800_000_000.0
SEAT = "flamingo-72904"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_RECYCLESEAT_DISABLE", raising=False)
    monkeypatch.delenv("BOB_DIGEST_HOME", raising=False)
    install = tmp_path / "install"
    home = tmp_path / "home"
    home.mkdir()
    (home / "registered-machines.json").write_text(
        json.dumps({"machines": ["flamingo", "marchhare"]})
    )
    adir = sw.queue_dir(install)
    adir.mkdir(parents=True)
    for name in (sw.ALIVE_FILE, sw.ENGINE_ALIVE_FILE):
        path = adir / name
        path.write_text("alive")
        os.utime(path, (NOW, NOW))
    return install, home


def ask(setup, **kw):
    install, home = setup
    args = dict(
        body=f"!recycleseat {SEAT} flamingo",
        nick="Jeeves",
        account=None,
        channel="#flamingo",
        local_machine="flamingo",
        qdir=rs.queue_dir(install),
        install_root=install,
        home=home,
        machine_of_nick=bobreport.machine_from_nick,
        now=NOW,
    )
    args.update(kw)
    return rs.decide(**args)


@pytest.mark.parametrize("source", ["workers", "worker_list"])
@pytest.mark.parametrize("roster_present", [True, False])
def test_working_seat_nacks_without_queueing(setup, source, roster_present):
    install, home = setup
    if not roster_present:
        (home / "registered-machines.json").unlink()
    ent = {"workers": {}, "worker_list": []}
    if source == "workers":
        ent["workers"]["72904"] = {"working_on": "MRB SimonBarnett/bobiverse#5890"}
    else:
        ent["worker_list"] = [
            {"nick": SEAT.upper(), "state": "doing", "work": "MRB SimonBarnett/bobiverse#5890"}
        ]
    bobreport.save_digest(home, {"machines": {"flamingo": ent}})
    before = bobreport.digest_path(home).read_bytes()
    d = ask(setup)
    assert not d.ok and d.reason == "busy"
    assert SEAT in d.line and "busy" in d.line and "working_on" in d.line
    assert not list(rs.queue_dir(install).glob("req-*.json"))
    assert bobreport.digest_path(home).read_bytes() == before


def test_unreadable_work_evidence_fails_closed(setup):
    install, home = setup
    bobreport.digest_path(home).write_text("not json")
    d = ask(setup)
    assert not d.ok and d.reason == "state_unavailable"
    assert SEAT in d.line
    assert not list(rs.queue_dir(install).glob("req-*.json"))


def test_busy_check_uses_shared_digest_home(setup, tmp_path, monkeypatch):
    _, home = setup
    shared = tmp_path / "digest"
    shared.mkdir()
    (shared / "registered-machines.json").write_text(json.dumps({"machines": ["flamingo"]}))
    monkeypatch.setenv("BOB_DIGEST_HOME", str(shared))
    bobreport.save_digest(shared, {"machines": {"flamingo": {
        "workers": {"72904": {"working_on": "FR SimonBarnett/bobiverse#5890"}}
    }}})
    assert not bobreport.digest_path(home).exists()
    assert ask(setup).reason == "busy"


def test_recent_ack_is_durable_case_insensitive_and_seat_specific(setup):
    install, _ = setup
    assert ask(setup).ok
    # Tray consumes the request; the ACK guard must survive that and ear restart.
    for request in rs.queue_dir(install).glob("req-*.json"):
        request.unlink()
    d = ask(setup, body=f"!recycleseat {SEAT.upper()} flamingo", now=NOW + 1)
    assert not d.ok and d.reason == "busy"
    assert SEAT.upper() in d.line and "cooldown" in d.line
    assert not list(rs.queue_dir(install).glob("req-*.json"))
    assert ask(setup, body="!recycleseat flamingo-72905 flamingo").ok


def test_cooldown_expires(setup):
    install, _ = setup
    assert ask(setup).ok
    later = NOW + rs.ACK_COOLDOWN_S
    for path in sw.queue_dir(install).iterdir():
        os.utime(path, (later, later))
    assert ask(setup, now=later).ok


def test_idle_target_acks_and_queues_despite_another_working_seat(setup):
    install, home = setup
    bobreport.save_digest(home, {"machines": {"flamingo": {
        "working_on": "MRB SimonBarnett/bobiverse#5890",
        "workers": {"72905": {"working_on": "MRB SimonBarnett/bobiverse#5890"}}
    }}})
    d = ask(setup)
    assert d.ok and f"ACK recycleseat {SEAT}" in d.line
    requests = list(rs.queue_dir(install).glob("req-*.json"))
    assert len(requests) == 1
    assert json.loads(requests[0].read_text())["nick"] == SEAT


def test_queue_failure_does_not_stamp_cooldown(setup, monkeypatch):
    original = rs.write_request

    def fail(*args, **kwargs):
        raise OSError("test queue failure")

    monkeypatch.setattr(rs, "write_request", fail)
    assert ask(setup).reason == "queue_error"
    monkeypatch.setattr(rs, "write_request", original)
    assert ask(setup).ok


@pytest.mark.parametrize("fail_on", ["ack", "req"])
def test_failed_atomic_publish_queues_nothing_and_allows_retry(setup, monkeypatch, fail_on):
    install, _ = setup
    original = rs.os.replace

    def fail(src, dst):
        if dst.name.startswith(f"{fail_on}-"):
            raise OSError("test publish failure")
        return original(src, dst)

    monkeypatch.setattr(rs.os, "replace", fail)
    assert ask(setup).reason == "queue_error"
    assert not list(rs.queue_dir(install).glob("req-*.json"))
    assert not list(rs.queue_dir(install).glob("ack-*.json"))
    monkeypatch.setattr(rs.os, "replace", original)
    assert ask(setup).ok


def test_corrupt_ack_stamp_fails_closed(setup):
    install, _ = setup
    qdir = rs.queue_dir(install)
    qdir.mkdir(parents=True)
    (qdir / f"ack-{SEAT}.json").write_text("not json")
    assert ask(setup).reason == "queue_error"
    assert not list(qdir.glob("req-*.json"))


def test_dry_run_does_not_stamp_cooldown(setup):
    assert ask(setup, write=False).ok
    assert ask(setup).ok


def test_non_target_is_silent_and_debug_logged(setup):
    messages = []
    d = ask(setup, local_machine="marchhare", debug=messages.append)
    assert d is None
    assert len(messages) == 1
    assert "ignore" in messages[0] and "flamingo" in messages[0]
    assert "marchhare" in messages[0] and SEAT in messages[0]


def test_ear_wires_busy_guard_and_debug_log(setup, monkeypatch):
    install, home = setup
    bobreport.save_digest(home, {"machines": {"flamingo": {
        "workers": {"72904": {"working_on": "MRB SimonBarnett/bobiverse#5890"}}
    }}})
    client = object.__new__(irc_agent.Client)
    client.args = SimpleNamespace(chair=False)
    client.original_nick = "Bob-flamingo"
    client.home = home
    client.debug = home / "debug.log"
    client._mine_nicks = lambda: {"bob-flamingo"}
    client._local_machine_id = lambda: "flamingo"
    client._install_root = lambda: install
    client._account_of = lambda n: None
    client._nick_modes_in_channel = lambda n, ch: set()
    replies = []
    client.send_privmsg_lines = replies.append
    monkeypatch.setattr(irc_agent.time, "sleep", lambda n: None)
    assert client._maybe_recycleseat("Jeeves", "#flamingo", f"!recycleseat {SEAT} flamingo",
                                    to_channel=True, to_me=False)
    assert len(replies) == 1 and "busy" in replies[0] and SEAT in replies[0]
    replies.clear()
    assert client._maybe_recycleseat("Jeeves", "#flamingo", "!recycleseat marchhare-123 marchhare",
                                    to_channel=True, to_me=False)
    assert not replies
    assert "marchhare-123" in client.debug.read_text()
