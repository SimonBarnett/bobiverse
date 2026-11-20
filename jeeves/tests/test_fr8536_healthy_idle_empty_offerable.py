"""FR #8536: idle_seats marks healthy idle when offerable queue is empty."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import bobreport
import registered_machines

MON = Path(__file__).resolve().parents[1] / "tools" / "monitor"
sys.path.insert(0, str(MON))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common" / "scripts"))

import idle_seats  # noqa: E402


def _write_digest(digest: Path, machines: dict) -> None:
    digest.mkdir(parents=True, exist_ok=True)
    doc = bobreport.empty_digest()
    for mid, workers in machines.items():
        doc["machines"][mid] = bobreport._empty_machine(mid)
        doc["machines"][mid]["workers"] = {
            str(pid): {"state": state, "nick": f"{mid}-{pid}"} for pid, state in workers.items()
        }
    bobreport.save_digest(digest, doc)


def test_fr8536_healthy_idle_needs_human_only(tmp_path, monkeypatch):
    chair = tmp_path / ".jeeves"
    digest = tmp_path / ".bobiverse"
    chair.mkdir()
    registered_machines.save_registered(digest, {"flamingo"})
    _write_digest(digest, {"flamingo": {17508: "idle", 19304: "idle"}})
    monkeypatch.setenv("BOB_DIGEST_HOME", str(digest))
    (digest / "queue.json").write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": [
                    {
                        "repo": "SimonBarnett/bobiverse",
                        "task": "FR",
                        "id": "#8499",
                        "needs_human": True,
                        "title": "stall",
                        "labels": ["feature-request"],
                        "line": "FR SimonBarnett/bobiverse#8499",
                    }
                ],
                "accepted": [],
                "done": [],
            }
        ),
        encoding="utf-8",
    )
    args = type("A", (), {"chair_home": str(chair), "digest_home": str(digest), "dry_run": False})()
    payload, code = idle_seats.check(args)
    assert code == 0, payload
    assert payload["ok"] is True
    assert payload["offerable_for_live_seats"] == 0
    assert payload.get("healthy_idle_empty_offerable") is True
    assert payload.get("queue_needs_human_only") is True
    joined = " ".join(payload.get("notes") or [])
    assert "do not recycle" in joined.lower() or "healthy" in joined.lower()


def test_fr8536_tipform_helper_mentions_queue_caption():
    hover = (
        Path(__file__).resolve().parents[2]
        / "bob"
        / "tray"
        / "src"
        / "Public"
        / "Get-BobTrayHover.ps1"
    )
    text = hover.read_text(encoding="utf-8")
    assert "FR #8536" in text
    assert "Format-BobTrayQueueIdleCaption" in text or "queue_needs_human_only" in text