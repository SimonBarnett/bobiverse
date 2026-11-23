"""FR #9471: startworker always ACK/NACK for the target machine (never silent on decide failure).

Marchhare class: engine.alive stale / HealEngine storm must not leave !startworker without a reply
when this ear owns the named machine. TipForm online_zero_workers (#9462) stays until workers>0.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import startworker as sw


def _fresh_tray(q: Path) -> None:
    q.mkdir(parents=True, exist_ok=True)
    (q / sw.ALIVE_FILE).write_text("tray", encoding="ascii")
    now = time.time()
    os.utime(q / sw.ALIVE_FILE, (now, now))


def test_fr9471_decide_nacks_engine_stale_for_named_online_target(tmp_path):
    q = tmp_path / "startworker"
    _fresh_tray(q)
    # no engine.alive -> engine_stale NACK (never None)
    d = sw.decide(
        body="!startworker agent marchhare",
        nick="Bob-redqueen",
        account="bob-redqueen",
        channel="#bobiverse",
        local_machine="marchhare",
        gate=sw.StartGate(2, 0),
        qdir=q,
        machine_of_nick=lambda n: "redqueen" if "redqueen" in (n or "").lower() else None,
        write=False,
    )
    assert d is not None
    assert d.ok is False
    assert d.reason == "engine_stale"
    assert d.line.startswith("NACK startworker:")


def test_fr9471_targets_local_helper():
    assert sw.targets_local("!startworker agent marchhare", "marchhare", "#bobiverse") is True
    assert sw.targets_local("!startworker agent flamingo", "marchhare", "#bobiverse") is False
    assert sw.targets_local("!startworker agent", "marchhare", "#marchhare") is True
    assert sw.targets_local("!startworker agent", "marchhare", "#bobiverse") is False
    assert sw.targets_local("hello", "marchhare", "#bobiverse") is False


def test_fr9471_maybe_startworker_nacks_on_decide_exception(monkeypatch, tmp_path):
    import irc_agent

    q = tmp_path / "sw"
    _fresh_tray(q)
    sent: list[str] = []

    class Fake:
        args = SimpleNamespace(chair=False)
        original_nick = "Bob-marchhare"
        home = tmp_path / "home"
        _sw_gate = sw.StartGate(2, 0)

        def _mine_nicks(self):
            return {"bob-marchhare"}

        def _local_machine_id(self):
            return "marchhare"

        def _install_root(self):
            return str(tmp_path)

        def _account_of(self, who):
            return "bob-redqueen"

        def _whois_hint(self, who):
            return None

        def send_privmsg_lines(self, line):
            sent.append(line)

        def whisper(self, who, line):
            sent.append(f"WHISPER {who} {line}")

    monkeypatch.setattr(sw, "queue_dir", lambda root: q)

    def boom(**kwargs):
        raise RuntimeError("synthetic decide failure")

    monkeypatch.setattr(sw, "decide", boom)

    bob = Fake()
    ok = irc_agent.Client._maybe_startworker(
        bob, "Bob-redqueen", "#bobiverse", "!startworker agent marchhare", to_channel=True, to_me=False
    )
    assert ok is True
    assert sent, "must reply NACK on decide exception for local target"
    assert any("NACK startworker:" in s and "decide failed" in s.lower() for s in sent)


def test_fr9471_healengine_storm_pins_forced_reload():
    cs = Path(__file__).resolve().parents[1] / "tray" / "dialogs" / "BobTray.cs"
    text = cs.read_text(encoding="utf-8")
    i = text.index("engineStarts > 3")
    window = text[i : i + 2200]
    assert "FR #9471" in window
    assert "ReloadEngine()" in window
    assert "engine.storm" in window
    assert "storm-forced-reload" in window


def test_fr9471_online_zero_workers_still_on_main():
    mon = Path(__file__).resolve().parents[2] / "jeeves" / "tools" / "monitor" / "online_zero_workers.py"
    assert mon.is_file()
    body = mon.read_text(encoding="utf-8")
    assert "online-zero-workers" in body
    assert "3180" in body
def test_fr9471_engine_storm_helper_in_startworker_ps1():
    ps1 = Path(__file__).resolve().parents[1] / "tray" / "tools" / "BobTrayStartWorker.ps1"
    text = ps1.read_text(encoding="utf-8")
    assert "function Get-BobTrayEngineStormAlert" in text
    assert "engine_restart_storm" in text
    watch = Path(__file__).resolve().parents[1] / "tray" / "tools" / "Watch-BobTray.ps1"
    w = watch.read_text(encoding="utf-8")
    assert "Get-BobTrayEngineStormAlert" in w
    assert "engine_restart_storm" in w
