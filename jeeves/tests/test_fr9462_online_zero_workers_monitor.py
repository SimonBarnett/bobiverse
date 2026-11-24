"""FR #9462: monitor EXIT 1 for online workers=[] + offerable_count>0."""
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
import online_zero_workers as oz  # noqa: E402


def _args(chair: Path, digest: Path):
    return SimpleNamespace(chair_home=str(chair), digest_home=str(digest), dry_run=False)


def _homes(tmp_path: Path):
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    digest.mkdir()
    return chair, digest


def _fresh_report(**extra):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc = {
        "ts": ts,
        "queue": {"unaccepted": [{"id": 1}], "accepted": [], "offerable_count": 17},
        "machines": {
            "flamingo": {
                "online": True,
                "workers": {
                    "1": {"nick": "flamingo-1", "state": "doing"},
                    "2": {"nick": "flamingo-2", "state": "doing"},
                },
            },
            "marchhare": {"online": True, "workers": {}},
            "redqueen": {"online": True, "worker_list": []},
        },
    }
    doc.update(extra)
    return doc


def test_collect_online_zero_with_offerable():
    machines = {
        "flamingo": {"online": True, "workers": [{"nick": "a"}]},
        "marchhare": {"online": True, "workers": {}},
        "offline": {"online": False, "workers": []},
        "unknown": {"online": True},  # no workers key => skip
    }
    found = oz.collect_online_zero_machines(machines, 17)
    assert [r["machine"] for r in found] == ["marchhare"]
    assert found[0]["fingerprint"] == "stall:online-zero-workers:marchhare"
    assert found[0]["offerable_count"] == 17


def test_collect_silent_without_offerable():
    machines = {"marchhare": {"online": True, "workers": []}}
    assert oz.collect_online_zero_machines(machines, 0) == []


def test_live_report_exit_1_names_machines(tmp_path, monkeypatch):
    chair, digest = _homes(tmp_path)
    monkeypatch.setattr(common, "fetch_live_report", lambda **_k: _fresh_report())
    payload, code = oz.check(_args(chair, digest))
    assert code == common.EXIT_FINDING
    assert payload["source"] == "live_report"
    assert set(payload["machine_ids"]) == {"marchhare", "redqueen"}
    assert "stall:online-zero-workers:marchhare" in payload["fingerprints"]
    assert "stall:online-zero-workers:redqueen" in payload["fingerprints"]
    assert "TipForm" in payload["remediation"]
    assert any("marchhare" in f for f in payload["findings"])


def test_live_report_exit_0_when_offerable_zero(tmp_path, monkeypatch):
    chair, digest = _homes(tmp_path)
    doc = _fresh_report()
    doc["queue"]["offerable_count"] = 0
    monkeypatch.setattr(common, "fetch_live_report", lambda **_k: doc)
    payload, code = oz.check(_args(chair, digest))
    assert code == common.EXIT_OK
    assert payload["machine_ids"] == []
    assert payload["ok"] is True


def test_local_digest_exit_1(tmp_path):
    chair, digest = _homes(tmp_path)
    (chair / "queue.json").write_text(
        json.dumps({"v": 1, "unaccepted": [], "accepted": [], "done": []}),
        encoding="utf-8",
    )
    dig = {
        "queue": {"offerable_count": 5},
        "machines": {
            "redqueen": {"online": True, "workers": [], "worker_list": []},
            "flamingo": {"online": True, "workers": [{"nick": "flamingo-1"}]},
        },
    }
    (digest / "digest.json").write_text(json.dumps(dig), encoding="utf-8")
    payload, code = oz.check(_args(chair, digest))
    assert code == common.EXIT_FINDING
    assert payload["source"] == "local_digest"
    assert payload["machine_ids"] == ["redqueen"]
    assert payload["fingerprints"] == ["stall:online-zero-workers:redqueen"]
