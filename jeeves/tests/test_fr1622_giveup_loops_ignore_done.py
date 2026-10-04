"""FR #1622: giveup_loops must not EXIT 1 on historical done[] giveup_count rows."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from repo_layout import REPO

MONITOR = REPO / "jeeves" / "tools" / "monitor"
SRC = (MONITOR / "giveup_loops.py").read_text(encoding="utf-8-sig")


def _run(chair: Path, digest: Path) -> tuple[int, dict]:
    py = MONITOR / "giveup_loops.py"
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


def _write_queue(chair: Path, *, unaccepted=None, accepted=None, done=None) -> None:
    chair.mkdir(parents=True, exist_ok=True)
    (chair / "queue.json").write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": list(unaccepted or []),
                "accepted": list(accepted or []),
                "done": list(done or []),
            }
        ),
        encoding="utf-8",
    )


def _write_digest(digest: Path, machines: dict) -> None:
    digest.mkdir(parents=True, exist_ok=True)
    (digest / "digest.json").write_text(json.dumps({"machines": machines}), encoding="utf-8")


def test_source_scopes_active_buckets_not_done():
    assert "queue_bucket_rows" in SRC
    assert '"unaccepted", "accepted"' in SRC or "'unaccepted', 'accepted'" in SRC
    # Must not treat done as an active hotspot bucket in the scan list.
    assert "FR #1622" in SRC
    assert "skipped_done" in SRC or "done[]" in SRC


def test_done_only_high_giveup_exits_0(tmp_path):
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    _write_queue(
        chair,
        done=[
            {
                "repo": "SimonBarnett/Club-Madeira",
                "id": "#2",
                "giveup_count": 3,
                "task": "FR",
            },
            {
                "repo": "SimonBarnett/bobiverse",
                "id": "#1043",
                "giveup_count": 2,
                "task": "FR",
            },
        ],
    )
    _write_digest(digest, {"marchhare": {"worker_list": [{"nick": "marchhare-1", "state": "idle"}]}})
    code, payload = _run(chair, digest)
    assert code == 0, payload
    assert payload["ok"] is True
    assert payload.get("hotspots") == {}
    assert int(payload.get("skipped_done_hotspots") or 0) >= 2
    notes = " ".join(payload.get("notes") or [])
    assert "done[]" in notes.lower() or "historical" in notes.lower()


def test_unaccepted_high_giveup_still_exits_1(tmp_path):
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    _write_queue(
        chair,
        unaccepted=[
            {
                "repo": "SimonBarnett/bobiverse",
                "id": "#9999",
                "giveup_count": 2,
                "task": "FR",
                "title": "ungated loop",
            }
        ],
        done=[{"repo": "SimonBarnett/bobiverse", "id": "#1043", "giveup_count": 2}],
    )
    _write_digest(digest, {"marchhare": {"worker_list": [{"nick": "marchhare-1", "state": "idle"}]}})
    code, payload = _run(chair, digest)
    assert code == 1, payload
    assert payload["ok"] is False
    assert any("9999" in f for f in payload.get("findings") or [])
    assert not any("1043" in f for f in payload.get("findings") or [])


def test_gated_pin_no_live_seats_skipped(tmp_path):
    """DEV1-pinned high giveup with zero DEV1 seats is gated, not a loop (FR #1622)."""
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    _write_queue(
        chair,
        unaccepted=[
            {
                "repo": "SimonBarnett/agentic_fomprep",
                "id": "#56",
                "giveup_count": 2,
                "task": "FR",
                "require_machine": "ce-priority-dev1",
            }
        ],
    )
    # Only marchhare seats live — no ce-priority-dev1.
    _write_digest(digest, {"marchhare": {"worker_list": [{"nick": "marchhare-1", "state": "idle"}]}})
    code, payload = _run(chair, digest)
    assert code == 0, payload
    assert payload["ok"] is True
    assert int(payload.get("skipped_gated_hotspots") or 0) >= 1
    assert payload.get("hotspots") == {}
