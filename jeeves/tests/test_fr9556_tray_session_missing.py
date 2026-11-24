"""FR #9556: stuck rule tray_session_missing when startworker NACK tray-not-logged-in."""

from __future__ import annotations

import json
from pathlib import Path

import startworker as sw
import stuck_job_sweep as sweep


NACK_TEXT = (
    "NACK startworker: nobody is logged in with the Bob tray running "
    "(start the tray from the Start menu)"
)


def test_fr9556_nack_text_and_reason_detect():
    assert sw.is_tray_session_missing_nack("no_interactive_session", "")
    assert sw.is_tray_session_missing_nack("", NACK_TEXT)
    assert sw.is_tray_session_missing_nack("tray-not-logged-in", "")
    assert not sw.is_tray_session_missing_nack("engine_stale", "Bob tray engine is not ticking")
    assert not sw.is_tray_session_missing_nack("cap", "max 4 workers")


def test_fr9556_classify_from_fixture_nack():
    found = sweep.classify_tray_session_missing(
        {},
        nacks=[
            {
                "machine": "marchhare",
                "reason": "no_interactive_session",
                "text": NACK_TEXT,
            }
        ],
    )
    assert len(found) == 1
    row = found[0]
    assert row["stuck_reason"] == "tray_session_missing"
    assert row["rule"] == "tray_session_missing"
    assert row["holder"] == "marchhare"
    assert row["machine"] == "marchhare"
    assert row["task"] == "MACHINE"
    assert row["state"] == "machine"
    assert row.get("needs_human") is False


def test_fr9556_classify_from_digest_machine_cue():
    machines = {
        "marchhare": {
            "online": True,
            "worker_list": [],
            "tray_session_missing": True,
            "startworker_nack_reason": "no_interactive_session",
            "startworker_nack_text": NACK_TEXT,
        },
        "flamingo": {"online": True, "worker_list": [{"nick": "flamingo-1"}]},
    }
    found = sweep.classify_tray_session_missing(machines)
    assert [r["machine"] for r in found] == ["marchhare"]
    assert found[0]["stuck_reason"] == "tray_session_missing"


def test_fr9556_supersedes_online_zero_workers():
    machines = {
        "marchhare": {
            "online": True,
            "workers": {},
            "startworker_nack_reason": "no_interactive_session",
            "startworker_nack_text": NACK_TEXT,
        }
    }
    zero = sweep.classify_empty_online_machines(machines, ungated_count=2)
    miss = sweep.classify_tray_session_missing(machines)
    kept = sweep.suppress_online_zero_when_tray_missing(zero, miss)
    assert miss and miss[0]["stuck_reason"] == "tray_session_missing"
    assert kept == []


def test_fr9556_stuck_lines_name_machine(tmp_path: Path):
    report = {
        "v": 1,
        "paused": "",
        "stuck": sweep.classify_tray_session_missing(
            {},
            nacks=[{"machine": "marchhare", "reason": "no_interactive_session", "text": NACK_TEXT}],
        ),
        "held": [],
        "classified": [],
        "actions": {},
    }
    (tmp_path / "stuck-report.json").write_text(json.dumps(report), encoding="utf-8")
    lines = sweep.format_stuck_lines(tmp_path)
    joined = "\n".join(lines)
    assert "machine=marchhare" in joined
    assert "rule=tray_session_missing" in joined
    digest = sweep.digest_stuck_section(tmp_path)
    assert any(d.get("rule") == "tray_session_missing" for d in digest)
    assert any(d.get("holder") == "marchhare" for d in digest)


def test_fr9556_startworker_decide_stamps_and_nacks(tmp_path: Path):
    qdir = tmp_path / "run" / "startworker"
    qdir.mkdir(parents=True)
    # no tray.alive -> no_interactive_session
    dec = sw.decide(
        body="!startworker agent marchhare",
        nick="bob-marchhare",
        account="bob-marchhare",
        channel="#marchhare",
        local_machine="marchhare",
        gate=sw.StartGate(),
        qdir=qdir,
        home=tmp_path,
        machine_of_nick=lambda n: "marchhare",
        chair_nicks=("jeeves",),
        owners=None,
        write=True,
    )
    assert dec is not None
    assert dec.ok is False
    assert dec.reason == "no_interactive_session"
    assert "nobody is logged in with the Bob tray" in dec.line
    stamp = sw.tray_session_missing_stamp(qdir)
    assert stamp is not None
    assert stamp.get("rule") == "tray_session_missing"
    assert stamp.get("machine") == "marchhare"
