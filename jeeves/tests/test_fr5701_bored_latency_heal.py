"""FR #5701: bored-latency stalls must !recycleseat the silent seat (IRC).

flamingo-64124 sat idle with lag_s=938 (no !bored). Detector correctly filed.
Chair must PRIVMSG ``!recycleseat <nick> <machine>`` so the remote tray ear
restarts the seat (same FR #5220 remote-ear pattern as author-only deadlock).
"""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import registered_machines
import stall_detectors as sd


def test_heal_bored_latency_enqueues_recycleseat_irc(tmp_path, monkeypatch):
    nick = "flamingo-64124"
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [{"nick": nick, "state": "idle"}]
    bobreport.save_digest(tmp_path, digest)
    install = tmp_path / "install"
    install.mkdir()
    now = 1_700_000.0
    lines = gitclaim.heal_bored_latency(
        tmp_path,
        idle={nick},
        last_bored={nick: now - 938},
        last_activity={},
        accepted=[],
        now=now,
        install_root=install,
    )
    assert any("bored-latency recycleseat=flamingo-64124" in x for x in lines), lines
    outbox = tmp_path / "chair-outbox.txt"
    if not outbox.is_file():
        outbox = Path(bobreport.fleet_digest_home(tmp_path)) / "chair-outbox.txt"
    text = outbox.read_text(encoding="utf-8") if outbox.is_file() else ""
    assert "!recycleseat flamingo-64124 flamingo" in text, text
    assert "PRIVMSG #bobiverse :" in text or "PRIVMSG #flamingo :" in text


def test_heal_bored_latency_cooldown_skips_second_fire(tmp_path, monkeypatch):
    nick = "flamingo-64124"
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [{"nick": nick, "state": "idle"}]
    bobreport.save_digest(tmp_path, digest)
    install = tmp_path / "install"
    install.mkdir()
    now = 1_700_000.0
    first = gitclaim.heal_bored_latency(
        tmp_path,
        idle={nick},
        last_bored={nick: now - 500},
        accepted=[],
        now=now,
        install_root=install,
    )
    assert first, first
    second = gitclaim.heal_bored_latency(
        tmp_path,
        idle={nick},
        last_bored={nick: now - 500},
        accepted=[],
        now=now + 60,
        install_root=install,
    )
    assert second == []


def test_heal_skips_accepted_and_fresh_bored(tmp_path, monkeypatch):
    nick = "flamingo-64124"
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo"})
    now = 1_700_000.0
    assert (
        gitclaim.heal_bored_latency(
            tmp_path,
            idle={nick},
            last_bored={nick: now - 10},
            accepted=[],
            now=now,
        )
        == []
    )
    assert (
        gitclaim.heal_bored_latency(
            tmp_path,
            idle={nick},
            last_bored={nick: now - 500},
            accepted=[{"accepted_by": nick, "repo": "x", "id": "#1"}],
            now=now,
        )
        == []
    )


def test_stall_scan_wires_bored_latency_heal():
    src = (
        Path(__file__).resolve().parents[2] / "common" / "scripts" / "chair_health.py"
    ).read_text(encoding="utf-8")
    scan = src[src.find("def _stall_scan") :]
    assert "heal_bored_latency" in scan
    assert "heal_mrb_reviewer_deadlock" in scan


def test_detector_still_fires_after_heal_pattern():
    """Heal restarts the seat; filing still records the stall (FR #5164 audit)."""
    now = 100_000.0
    late = sd.detect_bored_latency(
        {
            "now": now,
            "idle": {"flamingo-64124"},
            "last_bored": {"flamingo-64124": now - 938},
            "accepted": [],
        }
    )
    assert late and late[0]["id"] == sd.BORED_LATENCY_ID
    assert late[0]["evidence"]["lag_s"] == 938
