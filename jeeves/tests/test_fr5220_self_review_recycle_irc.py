"""FR #5220: author-only deadlock on one idle implementer must !recycleseat on IRC.

Local tray queue on the chair box never reaches flamingo. Jeeves must PRIVMSG
``!recycleseat <nick> <machine>`` so that machine's ear queues the recycle.
"""
from __future__ import annotations

import json
from pathlib import Path

import bobreport
import gitclaim
import registered_machines
import stall_detectors as sd

from test_fr5163_mrb_reviewer_deadlock import _mrb_row


def test_author_only_flamingo_enqueues_recycleseat_irc(tmp_path, monkeypatch):
    nick = "flamingo-48304"
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [{"nick": nick, "state": "idle"}]
    bobreport.save_digest(tmp_path, digest)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                _mrb_row(
                    repo="SimonBarnett/agentic_fomprep",
                    num=241,
                    author=nick,
                )
            ],
            "accepted": [],
            "done": [],
        },
    )
    install = tmp_path / "install"
    install.mkdir()
    lines = gitclaim.heal_mrb_reviewer_deadlock(
        tmp_path, install_root=install, now=1_700_000.0
    )
    assert any("recycleseat=flamingo-48304" in x for x in lines), lines
    outbox = tmp_path / "chair-outbox.txt"
    if not outbox.is_file():
        outbox = Path(bobreport.fleet_digest_home(tmp_path)) / "chair-outbox.txt"
    text = outbox.read_text(encoding="utf-8") if outbox.is_file() else ""
    assert "!recycleseat flamingo-48304 flamingo" in text, text
    # FR #5756: shop only (never #bobiverse).
    assert "PRIVMSG #flamingo :" in text
    assert "PRIVMSG #bobiverse :" not in text


def test_self_review_detector_silent_when_healed():
    snap = {
        "idle": {"flamingo-48304"},
        "live": {"flamingo-48304"},
        "unaccepted": [
            {
                "task": "MRB",
                "repo": "SimonBarnett/agentic_fomprep",
                "id": "#241",
                "url": "https://github.com/SimonBarnett/agentic_fomprep/pull/241",
                "author_seat": "flamingo-48304",
            }
        ],
        "deadlock_healed": True,
    }
    assert sd.detect_self_review_deadlock(snap) == []


def test_stall_scan_heals_before_file():
    src = (Path(__file__).resolve().parents[2] / "common" / "scripts" / "chair_health.py").read_text(
        encoding="utf-8"
    )
    scan = src[src.find("def _stall_scan") :]
    assert "heal_mrb_reviewer_deadlock" in scan
    assert "deadlock_healed" in scan
