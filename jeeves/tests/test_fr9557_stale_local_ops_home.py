"""FR #9557: empty/stale local ops home prefers live /bob/v1/report."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from repo_layout import REPO

MONITOR = REPO / "jeeves" / "tools" / "monitor"
sys.path.insert(0, str(MONITOR))

import _common as common  # noqa: E402
import idle_seats  # noqa: E402


def _fresh_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fresh_report(**extra):
    doc = {
        "ts": _fresh_ts(),
        "chairNick": "Jeeves",
        "queue": {
            "unaccepted": [{"id": 1, "task": "FR", "repo": "SimonBarnett/bobiverse"}],
            "accepted": [
                {
                    "id": 9526,
                    "task": "FR",
                    "nick": "flamingo-17068",
                    "accepted_by": "flamingo-17068",
                }
            ],
            "offerable_count": 12,
        },
        "machines": {
            "flamingo": {
                "workers": {
                    "17068": {
                        "state": "doing",
                        "nick": "flamingo-17068",
                        "pid": "17068",
                        "work": "FR SimonBarnett/bobiverse#9526",
                    },
                }
            },
            "redqueen": {
                "workers": {
                    "99": {"state": "idle", "nick": "redqueen-99", "pid": "99"},
                }
            },
        },
    }
    doc.update(extra)
    return doc


def _args(chair: Path, digest: Path):
    return SimpleNamespace(chair_home=str(chair), digest_home=str(digest), dry_run=False)


def _homes(tmp_path: Path):
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    digest.mkdir()
    return chair, digest


def test_digest_home_prefers_monitor_override(tmp_path, monkeypatch):
    # Allow pytest tmp paths through the ephemeral-home guard for this unit test.
    monkeypatch.setattr(common, "_is_ephemeral_test_home", lambda _p: False)
    mon = tmp_path / "monitor-home"
    seat = tmp_path / "seat-home"
    mon.mkdir()
    seat.mkdir()
    env = {
        "JEEVES_MONITOR_DIGEST_HOME": str(mon),
        "BOB_DIGEST_HOME": str(seat),
        "USERPROFILE": str(tmp_path / "user"),
    }
    assert common.digest_home(env) == mon
    env2 = {"BOB_DIGEST_HOME": str(seat), "USERPROFILE": str(tmp_path / "user")}
    assert common.digest_home(env2) == seat


def test_local_ops_stale_empty_queue(tmp_path):
    chair, digest = _homes(tmp_path)
    (chair / "queue.json").write_text(
        json.dumps({"unaccepted": [], "accepted": []}), encoding="utf-8"
    )
    (digest / "digest.json").write_text(json.dumps({"machines": {}}), encoding="utf-8")
    why = common.local_ops_stale_vs_live_report(chair, digest, _fresh_report())
    assert why == "empty_local_queue"


def test_local_ops_stale_seat_mismatch(tmp_path):
    chair, digest = _homes(tmp_path)
    # Local queue has some rows but digest has no workers while live ACC is busy.
    (chair / "queue.json").write_text(
        json.dumps({"unaccepted": [], "accepted": [{"id": 1}]}), encoding="utf-8"
    )
    (digest / "digest.json").write_text(json.dumps({"machines": {}}), encoding="utf-8")
    why = common.local_ops_stale_vs_live_report(chair, digest, _fresh_report())
    assert why == "seat_state_mismatch"


def test_local_ops_not_stale_when_report_stale(tmp_path):
    chair, digest = _homes(tmp_path)
    (chair / "queue.json").write_text(
        json.dumps({"unaccepted": [], "accepted": []}), encoding="utf-8"
    )
    stale = _fresh_report(ts="2020-01-01T00:00:00Z")
    assert common.local_ops_stale_vs_live_report(chair, digest, stale) == ""
    assert common.local_ops_stale_vs_live_report(chair, digest, None) == ""


def test_local_ops_authoritative_when_local_matches(tmp_path):
    chair, digest = _homes(tmp_path)
    report = _fresh_report()
    (chair / "queue.json").write_text(
        json.dumps(
            {
                "unaccepted": report["queue"]["unaccepted"],
                "accepted": report["queue"]["accepted"],
            }
        ),
        encoding="utf-8",
    )
    (digest / "digest.json").write_text(
        json.dumps(
            {
                "machines": {
                    "flamingo": {
                        "workers": {
                            "17068": {"nick": "flamingo-17068", "state": "doing"},
                        }
                    },
                    "redqueen": {
                        "workers": {
                            "99": {"nick": "redqueen-99", "state": "idle"},
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    assert common.local_ops_stale_vs_live_report(chair, digest, report) == ""


def test_local_ops_not_stale_when_local_has_unaccepted_and_workers(tmp_path):
    """MRB #9566: non-empty local must stay authoritative despite extra live ACC.

    ``live_acc > local_acc`` alone must not flip to seat_state_mismatch — that
    broke idle_seats unit tests (and would hijack healthy chair locals).
    """
    chair, digest = _homes(tmp_path)
    (chair / "queue.json").write_text(
        json.dumps(
            {
                "unaccepted": [
                    {
                        "id": 1,
                        "task": "FR",
                        "repo": "SimonBarnett/bobiverse",
                        "needs_human": True,
                    }
                ],
                "accepted": [],
            }
        ),
        encoding="utf-8",
    )
    (digest / "digest.json").write_text(
        json.dumps(
            {
                "machines": {
                    "win-mpre8vi4u6u": {
                        "workers": {
                            "20596": {
                                "nick": "win-mpre8vi4u6u-20596",
                                "state": "idle",
                            }
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    why = common.local_ops_stale_vs_live_report(chair, digest, _fresh_report())
    assert why == ""


def test_idle_seats_empty_local_prefers_live_report(tmp_path, monkeypatch):
    chair, digest = _homes(tmp_path)
    (chair / "queue.json").write_text(
        json.dumps({"unaccepted": [], "accepted": []}), encoding="utf-8"
    )
    (digest / "digest.json").write_text(json.dumps({"machines": {}}), encoding="utf-8")
    monkeypatch.setattr(common, "fetch_live_report", lambda **_k: _fresh_report())
    payload, code = idle_seats.check(_args(chair, digest))
    assert code == common.EXIT_FINDING
    assert payload["source"] == "live_report_stale_local"
    assert payload["stale_local_home"] == "empty_local_queue"
    nicks = [x["nick"] for x in payload["idle_seats"]]
    assert "redqueen-99" in nicks
    assert "flamingo-17068" not in nicks
    assert any("stale_local_home=empty_local_queue" in n for n in payload["notes"])


def test_idle_seats_soft_skip_when_live_unusable(tmp_path, monkeypatch):
    chair, digest = _homes(tmp_path)
    (chair / "queue.json").write_text(
        json.dumps({"unaccepted": [], "accepted": []}), encoding="utf-8"
    )
    (digest / "digest.json").write_text(json.dumps({"machines": {}}), encoding="utf-8")
    # Fresh enough to trip stale detection once, but incomplete for seat paint.
    # Use a report that is fresh with queue work, then make overlay unusable via
    # incomplete machines after staleness is computed — soft-skip path needs
    # live_report_is_fresh True for stale_why, then _live_report_unusable True.
    # Simplest: fetch returns None after we still need stale — patch staleness.
    monkeypatch.setattr(
        common,
        "local_ops_stale_vs_live_report",
        lambda *_a, **_k: "empty_local_queue",
    )
    monkeypatch.setattr(common, "fetch_live_report", lambda **_k: None)
    payload, code = idle_seats.check(_args(chair, digest))
    assert code == common.EXIT_OK
    assert payload["skipped"] == "stale_local_home"
    assert payload["stale_local_home"] == "empty_local_queue"
    assert payload["source"] == "skipped_stale_local"
    assert payload["idle_seats"] == []
    assert payload["findings"] == []


def test_idle_seats_authoritative_local_keeps_local_path(tmp_path, monkeypatch):
    """Non-empty local that matches live stays on the local digest path."""
    chair, digest = _homes(tmp_path)
    # Live report mirrors local so local_ops_stale_vs_live_report returns ''.
    report = {
        "ts": _fresh_ts(),
        "chairNick": "Jeeves",
        "queue": {
            "unaccepted": [{"id": 1, "task": "FR", "repo": "SimonBarnett/bobiverse"}],
            "accepted": [],
            "offerable_count": 1,
        },
        "machines": {
            "redqueen": {
                "workers": {
                    "99": {
                        "state": "idle",
                        "nick": "redqueen-99",
                        "pid": "99",
                    }
                }
            }
        },
    }
    (chair / "queue.json").write_text(
        json.dumps(
            {
                "unaccepted": [{"id": 1, "task": "FR", "repo": "SimonBarnett/bobiverse"}],
                "accepted": [],
            }
        ),
        encoding="utf-8",
    )
    (digest / "digest.json").write_text(
        json.dumps(
            {
                "machines": {
                    "redqueen": {
                        "workers": {
                            "99": {
                                "state": "idle",
                                "nick": "redqueen-99",
                                "pid": "99",
                            }
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    called = {"n": 0}

    def _fetch(**_k):
        called["n"] += 1
        return report

    monkeypatch.setattr(common, "fetch_live_report", _fetch)
    payload, code = idle_seats.check(_args(chair, digest))
    assert called["n"] >= 1  # staleness probe
    assert payload.get("source") != "live_report_stale_local"
    assert payload.get("skipped") != "stale_local_home"
    # Local path: idle + offerable unaccepted → finding
    assert code == common.EXIT_FINDING
    assert any(x["nick"] == "redqueen-99" for x in payload["idle_seats"])
