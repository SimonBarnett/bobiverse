"""FR #9849: local idle/accepted ghosts soft-ok when live /bob/v1/report shows busy."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import bobreport
import registered_machines

MONITOR = Path(__file__).resolve().parents[1] / "tools" / "monitor"
sys.path.insert(0, str(MONITOR))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common" / "scripts"))

import _common as common  # noqa: E402
import idle_seats  # noqa: E402
import queue_flow  # noqa: E402


def _fresh_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _args(chair: Path, digest: Path):
    return SimpleNamespace(chair_home=str(chair), digest_home=str(digest), dry_run=False)


def _write_digest(digest: Path, machines: dict) -> None:
    digest.mkdir(parents=True, exist_ok=True)
    doc = bobreport.empty_digest()
    for mid, workers in machines.items():
        doc["machines"][mid] = bobreport._empty_machine(mid)
        doc["machines"][mid]["workers"] = {
            str(pid): {"state": state, "nick": f"{mid}-{pid}"}
            for pid, state in workers.items()
        }
    bobreport.save_digest(digest, doc)


def _live_busy_report(*, idle_also: bool = False):
    """Live report: flamingo-20596 doing + accepted>0 (contradicts local idle paint)."""
    machines = {
        "flamingo": {
            "workers": {
                "20596": {
                    "state": "doing",
                    "nick": "flamingo-20596",
                    "pid": "20596",
                    "work": "FIX SimonBarnett/bobiverse#9842",
                }
            }
        }
    }
    if idle_also:
        machines["redqueen"] = {
            "workers": {
                "99": {"state": "idle", "nick": "redqueen-99", "pid": "99"},
            }
        }
    return {
        "ts": _fresh_ts(),
        "chairNick": "Jeeves",
        "queue": {
            "unaccepted": [
                {
                    "id": 99,
                    "task": "FR",
                    "repo": "SimonBarnett/bobiverse",
                    "line": "FR SimonBarnett/bobiverse#99",
                }
            ],
            "accepted": [
                {
                    "id": 9842,
                    "task": "FIX",
                    "nick": "flamingo-20596",
                    "accepted_by": "flamingo-20596",
                }
            ],
            "offerable_count": 1,
        },
        "machines": machines,
    }


def test_local_idle_contradicted_by_live_helper():
    report = _live_busy_report()
    ghosts = common.local_idle_contradicted_by_live(
        ["flamingo-20596", "redqueen-99"], report
    )
    assert ghosts == {"flamingo-20596"}
    assert common.local_idle_contradicted_by_live(["flamingo-20596"], None) == set()
    stale = dict(report)
    stale["ts"] = "2020-01-01T00:00:00Z"
    assert common.local_idle_contradicted_by_live(["flamingo-20596"], stale) == set()


def test_idle_seats_soft_ok_when_live_shows_local_idles_busy(tmp_path, monkeypatch):
    """Local digest paints idle+offerable EXIT 1; live says those nicks are doing => EXIT 0."""
    chair = tmp_path / ".jeeves"
    digest = tmp_path / ".bobiverse"
    chair.mkdir()
    registered_machines.save_registered(digest, {"flamingo", "marchhare"})
    # Local ghost: flamingo idle while live shows doing + accepted.
    _write_digest(digest, {"flamingo": {20596: "idle"}, "marchhare": {1: "doing"}})
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
                        "title": "FR: real work",
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
    monkeypatch.setattr(common, "fetch_live_report", lambda **_k: _live_busy_report())
    payload, code = idle_seats.check(_args(chair, digest))
    assert code == common.EXIT_OK, payload
    assert payload["ok"] is True
    assert payload.get("local_stale") is True
    assert "flamingo-20596" in (payload.get("local_stale_idle_nicks") or [])
    assert payload["idle_seats"] == []
    assert payload["findings"] == []
    assert any("local_stale" in n and "FR #9849" in n for n in (payload.get("notes") or []))


def test_idle_seats_keeps_real_idle_when_only_some_are_ghosts(tmp_path, monkeypatch):
    """Drop live-busy ghosts; remaining real idle + offerable still EXIT 1."""
    chair = tmp_path / ".jeeves"
    digest = tmp_path / ".bobiverse"
    chair.mkdir()
    registered_machines.save_registered(digest, {"flamingo", "redqueen"})
    _write_digest(
        digest,
        {"flamingo": {20596: "idle"}, "redqueen": {99: "idle"}},
    )
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
                        "title": "FR: real work",
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
    monkeypatch.setattr(
        common, "fetch_live_report", lambda **_k: _live_busy_report(idle_also=True)
    )
    payload, code = idle_seats.check(_args(chair, digest))
    assert code == common.EXIT_FINDING, payload
    nicks = [x["nick"] for x in payload["idle_seats"]]
    assert "redqueen-99" in nicks
    assert "flamingo-20596" not in nicks
    assert payload.get("local_stale") is True


def test_queue_flow_soft_ok_true_starve_when_live_busy(tmp_path, monkeypatch):
    """queue_flow true-starve soft-ok when local idle nicks are doing on live report."""
    chair = tmp_path / ".jeeves"
    digest = tmp_path / ".bobiverse"
    chair.mkdir()
    registered_machines.save_registered(digest, {"flamingo"})
    _write_digest(digest, {"flamingo": {20596: "idle"}})
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
                        "title": "FR: real work",
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
    live = _live_busy_report()
    monkeypatch.setattr(common, "fetch_live_report", lambda **_k: live)
    monkeypatch.setattr(queue_flow, "fetch_live_report", lambda **_k: live)
    payload, code = queue_flow.check(_args(chair, digest))
    assert code == common.EXIT_OK, payload
    assert payload["ok"] is True
    assert not any("true starve" in f for f in (payload.get("findings") or []))
    assert payload.get("local_stale") is True
    assert any("local_stale" in n and "FR #9849" in n for n in (payload.get("notes") or []))
