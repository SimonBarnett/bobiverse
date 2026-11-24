"""FR #9644: idle+offerable EXIT 1 fingerprints idle_with_open_work and chair-heals."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

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


def _args(chair: Path, digest: Path, **extra):
    ns = SimpleNamespace(
        chair_home=str(chair),
        digest_home=str(digest),
        dry_run=False,
        intervene=False,
        intervene_dry_run=False,
        ear_outbox="",
        force_needs_human=False,
        pace_s=0.0,
        truncate_outbox=False,
        no_chair_heal=False,
    )
    for k, v in extra.items():
        setattr(ns, k, v)
    return ns


def test_fingerprint_idle_with_open_work_on_finding(tmp_path, monkeypatch):
    chair = tmp_path / ".jeeves"
    digest = tmp_path / ".bobiverse"
    chair.mkdir()
    registered_machines.save_registered(digest, {"flamingo", "redqueen"})
    _write_digest(digest, {"flamingo": {17068: "idle"}, "redqueen": {1: "doing"}})
    monkeypatch.setenv("BOB_DIGEST_HOME", str(digest))
    (digest / "queue.json").write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": [
                    {
                        "repo": "SimonBarnett/bobiverse",
                        "task": "MRB",
                        "id": "#9610",
                        "title": "MRB tip",
                        "labels": [],
                        "line": "MRB SimonBarnett/bobiverse#9610",
                        "url": "https://github.com/SimonBarnett/bobiverse/pull/9610",
                        "mergeable": True,
                    }
                ],
                "accepted": [],
                "done": [],
            }
        ),
        encoding="utf-8",
    )
    payload, code = idle_seats.check(_args(chair, digest))
    assert code == 1, payload
    assert payload["ok"] is False
    assert payload.get("fingerprint") == idle_seats.IDLE_WITH_OPEN_WORK_FP
    assert idle_seats.IDLE_WITH_OPEN_WORK_FP in (payload.get("fingerprints") or [])
    assert "idle_with_open_work" in (payload["findings"][0] if payload["findings"] else "")


def test_healthy_idle_has_no_fingerprint(tmp_path, monkeypatch):
    chair = tmp_path / ".jeeves"
    digest = tmp_path / ".bobiverse"
    chair.mkdir()
    registered_machines.save_registered(digest, {"flamingo"})
    _write_digest(digest, {"flamingo": {17068: "idle"}})
    monkeypatch.setenv("BOB_DIGEST_HOME", str(digest))
    (digest / "queue.json").write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": [
                    {
                        "repo": "SimonBarnett/bobiverse",
                        "task": "FR",
                        "id": "#1",
                        "needs_human": True,
                        "title": "human",
                        "labels": ["needs-human"],
                        "line": "FR SimonBarnett/bobiverse#1",
                    }
                ],
                "accepted": [],
                "done": [],
            }
        ),
        encoding="utf-8",
    )
    payload, code = idle_seats.check(_args(chair, digest))
    assert code == 0, payload
    assert payload.get("fingerprint") in (None, "")
    assert not payload.get("fingerprints")


def test_main_chair_heal_calls_push_idle(tmp_path, monkeypatch):
    """EXIT 1 path must attempt push_idle_offers_via_chair_outbox (not report-only)."""
    chair = tmp_path / ".jeeves"
    digest = tmp_path / ".bobiverse"
    chair.mkdir()
    registered_machines.save_registered(digest, {"flamingo"})
    _write_digest(digest, {"flamingo": {17068: "idle"}})
    monkeypatch.setenv("BOB_DIGEST_HOME", str(digest))
    (digest / "queue.json").write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": [
                    {
                        "repo": "SimonBarnett/bobiverse",
                        "task": "FR",
                        "id": "#99",
                        "title": "work",
                        "labels": ["feature-request"],
                        "line": "FR SimonBarnett/bobiverse#99",
                    }
                ],
                "accepted": [],
                "done": [],
            }
        ),
        encoding="utf-8",
    )
    calls = {"n": 0, "home": None}

    def _fake_push(home, **kwargs):
        calls["n"] += 1
        calls["home"] = home
        return 1

    # Patch the heal helper so check() still uses real gitclaim for offerable math.
    def _fake_heal(home):
        return _fake_push(home)

    monkeypatch.setattr(idle_seats, "_chair_heal_idle_offers", _fake_heal)

    code = idle_seats.main(
        [
            "--chair-home",
            str(chair),
            "--digest-home",
            str(digest),
            "--no-intervene",
        ]
    )
    assert code == 1
    assert calls["n"] == 1
    assert calls["home"] is not None


def test_agents_cast_iron_mentions_9644_next_to_9627():
    agents = Path(__file__).resolve().parents[1] / "AGENTS.md"
    text = agents.read_text(encoding="utf-8")
    assert "9627" in text
    assert "9644" in text
    assert "idle_with_open_work" in text
    # 9644 appears near 9627 (same CAST IRON block).
    i9627 = text.index("9627")
    i9644 = text.index("9644")
    assert abs(i9644 - i9627) < 1200
