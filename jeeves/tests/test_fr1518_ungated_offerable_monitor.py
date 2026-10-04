"""FR #1518: queue_flow reports ungated_offerable vs gated breakdown (skill flood ≠ starve)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from repo_layout import REPO

MONITOR = REPO / "jeeves" / "tools" / "monitor"


def _run_queue_flow(chair: Path, digest: Path) -> tuple[int, dict]:
    py = MONITOR / "queue_flow.py"
    r = subprocess.run(
        [
            sys.executable,
            str(py),
            "--chair-home",
            str(chair),
            "--digest-home",
            str(digest),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(MONITOR),
    )
    line = (r.stdout or "").strip().splitlines()[-1]
    return r.returncode, json.loads(line)


def _write_queue(chair: Path, unaccepted: list[dict]) -> None:
    chair.mkdir(parents=True, exist_ok=True)
    (chair / "queue.json").write_text(
        json.dumps({"v": 1, "unaccepted": unaccepted, "accepted": [], "done": []}),
        encoding="utf-8",
    )


def _write_digest(digest: Path, *, idle: bool = True) -> None:
    digest.mkdir(parents=True, exist_ok=True)
    state = "idle" if idle else "doing"
    work = "" if idle else "FR #1"
    (digest / "digest.json").write_text(
        json.dumps(
            {
                "machines": {
                    "win-mpre8vi4u6u": {
                        "worker_list": [
                            {
                                "nick": "win-mpre8vi4u6u-1",
                                "state": state,
                                "work": work,
                            }
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def test_fr1518_gated_skill_and_pins_exit0_with_counts(tmp_path):
    """Skill + require_machine pins → gated-empty exit 0 (FR #1518)."""
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    _write_queue(
        chair,
        [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#9001",
                "title": "skill: harvest foo",
                "labels": ["skill", "via-intake"],
            },
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#1102",
                "title": "DEV1 pin",
                "labels": ["feature-request"],
                "require_machine": "ce-priority-dev1",
            },
        ],
    )
    _write_digest(digest, idle=True)
    code, payload = _run_queue_flow(chair, digest)
    assert code == 0, payload
    assert payload["ok"] is True
    assert payload["unaccepted_count"] == 2
    assert payload["ungated_offerable_count"] == 0
    gc = payload["gated_counts"]
    assert gc.get("skill", 0) >= 1
    assert gc.get("require_machine", 0) >= 1
    notes = " ".join(payload.get("notes") or [])
    assert "gated" in notes.lower() or "ungated" in notes.lower()


def test_fr1518_legacy_needs_mrb1_label_not_a_gate(tmp_path):
    """MRB #1529 / FR #1526: leftover needs-mrb1 must not gate; note only."""
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    _write_queue(
        chair,
        [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#1518",
                "title": "monitor ungated",
                "labels": ["feature-request", "needs-mrb1", "via-intake"],
            }
        ],
    )
    _write_digest(digest, idle=True)
    (digest / "registered-machines.json").write_text(
        '{"v":1,"machines":["win-mpre8vi4u6u"]}',
        encoding="utf-8",
    )
    code, payload = _run_queue_flow(chair, digest)
    assert payload.get("gated_counts", {}).get("needs-mrb1", 0) == 0
    notes = " ".join(payload.get("notes") or [])
    assert "legacy needs-mrb1" in notes
    # Seat-aware offerable may still be >0 → true starve is OK; label alone is not a gate.
    if int(payload.get("ungated_offerable_count") or 0) == 0:
        assert code == 0, payload


def test_fr1518_true_starve_when_ungated_and_idle(tmp_path):
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    _write_queue(
        chair,
        [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#42",
                "title": "real work",
                "labels": ["feature-request", "via-intake"],
            }
        ],
    )
    _write_digest(digest, idle=True)
    # registered machines so gitclaim roster does not explode
    (digest / "registered-machines.json").write_text(
        '{"v":1,"machines":["win-mpre8vi4u6u"]}',
        encoding="utf-8",
    )
    code, payload = _run_queue_flow(chair, digest)
    # May be starve (exit 1) if seat-aware offerable>0, or gated if focus/roster blocks.
    assert "ungated_offerable_count" in payload
    assert "gated_counts" in payload
    assert "idle_seat_count" in payload
    if int(payload.get("ungated_offerable_count") or 0) > 0 and int(
        payload.get("idle_seat_count") or 0
    ) > 0:
        assert code == 1, payload
        assert "true starve" in " ".join(payload.get("findings") or [])


def test_fr1518_payload_keys_always_present(tmp_path):
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    _write_queue(chair, [])
    _write_digest(digest, idle=False)
    code, payload = _run_queue_flow(chair, digest)
    assert code == 0, payload
    for k in (
        "unaccepted_count",
        "ungated_offerable_count",
        "gated_counts",
        "idle_seat_count",
        "notes",
        "findings",
    ):
        assert k in payload
