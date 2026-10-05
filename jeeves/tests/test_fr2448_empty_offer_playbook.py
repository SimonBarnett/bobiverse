"""FR #2448: empty-offer ops playbook + sustained pin-only starve monitor."""
from __future__ import annotations

import json
import time
from pathlib import Path

from repo_layout import ROOT

import queue_flow

DOC = ROOT / "jeeves/docs/empty-offer-playbook.md"
MONITOR = ROOT / "jeeves/docs/monitoring.md"
TROUBLE = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-troubleshooting/SKILL.md"


def test_fr2448_playbook_doc_points_at_log_fields_and_2446():
    assert DOC.is_file()
    text = DOC.read_text(encoding="utf-8")
    for needle in (
        "require_machine",
        "ledger",
        "out-of-focus",
        "format_empty_offer_detail",
        "seat-ledger",
        "#2446",
        "nothing queued",
        "shop workers",
    ):
        assert needle in text, needle
    raw = DOC.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.endswith(b"\n")


def test_fr2448_monitoring_and_troubleshooting_link_playbook():
    mon = MONITOR.read_text(encoding="utf-8")
    assert "empty-offer-playbook" in mon or "FR #2448" in mon
    trouble = TROUBLE.read_text(encoding="utf-8")
    assert "2448" in trouble or "empty-offer-playbook" in trouble
    assert "require_machine" in trouble


def _args(chair: Path, digest: Path):
    class A:
        pass

    a = A()
    a.chair_home = str(chair)
    a.digest_home = str(digest)
    a.dry_run = False
    return a


def test_fr2448_queue_flow_sustained_pin_only_finding(tmp_path, monkeypatch):
    """When unaccepted pins remain and idle seats see offerable=0 for >10m, EXIT 1."""
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    chair.mkdir()
    digest.mkdir()
    # Pins only for a machine with zero shop workers; idle seats elsewhere see offerable=0.
    (chair / "queue.json").write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": [
                    {
                        "repo": "SimonBarnett/bobiverse",
                        "task": "FR",
                        "id": "#1102",
                        "require_machine": "ce-priority-dev1",
                    },
                    {
                        "repo": "SimonBarnett/agentic_fomprep",
                        "task": "FR",
                        "id": "#56",
                        "require_machine": "ce-priority-dev1",
                    },
                ],
                "accepted": [],
                "done": [],
            }
        ),
        encoding="utf-8",
    )
    (digest / "digest.json").write_text(
        json.dumps(
            {
                "machines": {
                    "win-mpre8vi4u6u": {
                        "worker_list": [
                            {"nick": "win-mpre8vi4u6u-1", "state": "idle", "work": ""}
                        ]
                    },
                    "marchhare": {
                        "worker_list": [
                            {"nick": "marchhare-1", "state": "idle", "work": ""}
                        ]
                    },
                    "ce-priority-dev1": {"worker_list": []},
                }
            }
        ),
        encoding="utf-8",
    )

    t0 = 1_700_000_000.0
    monkeypatch.setattr(queue_flow.time, "time", lambda: t0)
    payload1, code1 = queue_flow.check(_args(chair, digest))
    assert code1 == 0, payload1
    assert payload1.get("ok") is True
    assert int(payload1.get("unaccepted_count") or 0) == 2
    assert int(payload1.get("offerable_count") or 0) == 0

    # Still under 10 minutes: informational only.
    monkeypatch.setattr(queue_flow.time, "time", lambda: t0 + 60)
    payload2, code2 = queue_flow.check(_args(chair, digest))
    assert code2 == 0, payload2

    # Past 10 minutes: finding.
    monkeypatch.setattr(queue_flow.time, "time", lambda: t0 + 601)
    payload3, code3 = queue_flow.check(_args(chair, digest))
    assert code3 == 1, payload3
    assert payload3.get("ok") is False
    joined = " ".join(payload3.get("findings") or [])
    assert "pin-only empty offer" in joined.lower() or "require_machine" in joined.lower()
    assert "2448" in joined or "10m" in joined or "600" in joined


def test_fr2448_queue_flow_clears_starve_state_when_queue_empty(tmp_path, monkeypatch):
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    chair.mkdir()
    digest.mkdir()
    q = chair / "queue.json"
    q.write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": [
                    {
                        "repo": "SimonBarnett/bobiverse",
                        "task": "FR",
                        "id": "#1",
                        "require_machine": "ce-priority-dev1",
                    }
                ],
                "accepted": [],
                "done": [],
            }
        ),
        encoding="utf-8",
    )
    (digest / "digest.json").write_text(
        json.dumps(
            {
                "machines": {
                    "win-mpre8vi4u6u": {
                        "worker_list": [
                            {"nick": "win-mpre8vi4u6u-1", "state": "idle", "work": ""}
                        ]
                    },
                    "ce-priority-dev1": {"worker_list": []},
                }
            }
        ),
        encoding="utf-8",
    )
    t0 = 2_000_000_000.0
    monkeypatch.setattr(queue_flow.time, "time", lambda: t0)
    queue_flow.check(_args(chair, digest))
    state = chair / "monitor-empty-offer-starve.json"
    assert state.is_file()

    q.write_text(json.dumps({"v": 1, "unaccepted": [], "accepted": [], "done": []}), encoding="utf-8")
    monkeypatch.setattr(queue_flow.time, "time", lambda: t0 + 10)
    payload, code = queue_flow.check(_args(chair, digest))
    assert code == 0, payload
    assert not state.is_file()
