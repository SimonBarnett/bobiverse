"""FR #6917: keep the assigned FROM-footer outbox alive; never guess a newer run dir."""
from __future__ import annotations

import shutil
from pathlib import Path

import bob_worker as bw


def test_ensure_outbox_recreates_vanished_run_dir(tmp_path: Path):
    run = tmp_path / "run" / "worker-marchhare-17876-27584879"
    out = run / "outbox.txt"
    run.mkdir(parents=True)
    out.write_text("ACK FR x/y#1\n", encoding="utf-8")
    shutil.rmtree(run)
    assert not run.exists()
    got = bw.ensure_outbox(out)
    assert got == out
    assert out.is_file()
    assert run.is_dir()


def test_format_from_stamps_live_outbox_and_replaces_stale_footer(tmp_path: Path):
    live = tmp_path / "run" / "worker-marchhare-17876-27584879" / "outbox.txt"
    stale = tmp_path / "run" / "worker-marchhare-999-deadbeef" / "outbox.txt"
    newer = tmp_path / "run" / "worker-marchhare-12044-30fd78bb"
    newer.mkdir(parents=True)
    (newer / "outbox.txt").write_text("", encoding="utf-8")
    line = bw.format_from(
        "Jeeves",
        "#marchhare",
        "marchhare-17876: FR SimonBarnett/bobiverse#6917 x [outbox: %s]" % stale,
        outbox=live,
    )
    assert str(live) in line
    assert str(stale) not in line
    assert str(newer / "outbox.txt") not in line
    assert line.count("[outbox:") == 1
    assert live.is_file()


def test_relay_deliver_recreates_assigned_outbox_not_newest_sibling(tmp_path: Path):
    assigned = tmp_path / "worker-marchhare-17876-27584879"
    sibling = tmp_path / "worker-marchhare-12044-30fd78bb"
    sibling.mkdir(parents=True)
    (sibling / "outbox.txt").write_text("NEW\n", encoding="utf-8")
    assigned.mkdir(parents=True)
    shutil.rmtree(assigned)
    got: list[str] = []

    def inject(line: str) -> bool:
        got.append(line)
        return True

    relay = bw.Relay(lambda *_a: None, persist_dir=assigned)
    relay.set_target(inject)
    status = relay.deliver(
        "Jeeves",
        "#marchhare",
        "marchhare-17876: FR SimonBarnett/bobiverse#6917 https://example/issues/6917",
    )
    assert status == "injected"
    assert (assigned / "outbox.txt").is_file()
    assert got and str(assigned / "outbox.txt") in got[0]
    assert str(sibling / "outbox.txt") not in got[0]


def test_drain_outbox_recreates_file_after_atomic_move(tmp_path: Path):
    run = tmp_path / "worker-x"
    path = run / "outbox.txt"
    bw.ensure_outbox(path)
    path.write_text("PRIVMSG #flamingo :hello\n", encoding="utf-8")
    sent: list[tuple[str, str]] = []

    class Irc:
        shop = "#flamingo"

        def say(self, target, text):
            sent.append((target, text))
            return True

    n = bw.drain_outbox(path, Irc(), lambda *_a: None)
    assert n == 1
    assert path.is_file()
    assert run.is_dir()
    assert sent == [("#flamingo", "hello")]
