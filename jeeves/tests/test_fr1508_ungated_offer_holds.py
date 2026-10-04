"""FR #1508: ungated offer hold-ups — false DEV1 pins, orphan doing, focus prune, zero-seat alert."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import bobreport
import focus_ignore as fi
import gitclaim
from repo_layout import REPO

MONITOR = REPO / "jeeves" / "tools" / "monitor"


def _roster(home: Path) -> None:
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["win-mpre8vi4u6u","ce-priority-dev1"]}',
        encoding="utf-8",
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None


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


def test_body_mention_of_require_machine_does_not_pin(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    mid = gitclaim.infer_require_machine(
        title="FR: bobiverse seats idle — prune closed focus",
        body=(
            "Evidence: queue only has require_machine=ce-priority-dev1 pins "
            "while ce-priority-dev1 has zero seats."
        ),
        labels=["feature-request", "via-intake"],
        repo="SimonBarnett/bobiverse",
        ident="#1508",
    )
    assert mid == ""


def test_title_ce_priority_dev1_still_pins(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    mid = gitclaim.infer_require_machine(
        title="chair: stamp require_machine=ce-priority-dev1 on ce-priority UAT #0",
        body="",
        labels=["via-intake"],
        repo="SimonBarnett/bobiverse",
        ident="#1102",
    )
    assert mid == "ce-priority-dev1"


def test_wp0_live_in_body_still_pins(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    mid = gitclaim.infer_require_machine(
        title="FR: WP0 live proof",
        body="PRIORITY_WP0_INSTANCE = ce-priority-dev for shell compile",
        labels=["feature-request"],
        repo="SimonBarnett/agentic_fomprep",
        ident="#56",
    )
    assert mid == "ce-priority-dev1"


def test_clear_orphan_digest_mrb_doing(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    doc = bobreport.empty_digest()
    doc["machines"]["win-mpre8vi4u6u"] = {
        "id": "win-mpre8vi4u6u",
        "online": True,
        "worker_list": [
            {
                "nick": "win-mpre8vi4u6u-20596",
                "state": "doing",
                "work": "bobiverse MRB #1476",
                "updated": "2026-10-04T07:31:49Z",
            }
        ],
        "workers": {
            "20596": {"state": "doing", "working_on": "bobiverse MRB #1476"},
        },
    }
    bobreport.save_digest(tmp_path, doc)

    def pr_exists(repo, num):
        return False  # merged

    n = gitclaim.clear_orphan_digest_mrb_doing(tmp_path, pr_exists=pr_exists)
    assert n == 1
    assert gitclaim.worker_working_on(tmp_path, "win-mpre8vi4u6u-20596") == ""
    ent = bobreport.load_digest(tmp_path)["machines"]["win-mpre8vi4u6u"]
    assert ent["worker_list"][0]["state"] == "idle"
    assert ent["worker_list"][0]["work"] == ""


def test_clear_orphan_digest_keeps_open_mrb(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    doc = bobreport.empty_digest()
    doc["machines"]["win-mpre8vi4u6u"] = {
        "id": "win-mpre8vi4u6u",
        "online": True,
        "worker_list": [
            {
                "nick": "win-mpre8vi4u6u-20596",
                "state": "doing",
                "work": "bobiverse MRB #9999",
                "updated": "2026-10-04T07:31:49Z",
            }
        ],
        "workers": {
            "20596": {"state": "doing", "working_on": "bobiverse MRB #9999"},
        },
    }
    bobreport.save_digest(tmp_path, doc)

    def pr_exists(repo, num):
        return str(num) == "9999"

    n = gitclaim.clear_orphan_digest_mrb_doing(tmp_path, pr_exists=pr_exists)
    assert n == 0
    # Prefer worker_list (canonical); legacy workers.working_on is optional.
    ent = bobreport.load_digest(tmp_path)["machines"]["win-mpre8vi4u6u"]
    assert ent["worker_list"][0]["state"] == "doing"
    assert "9999" in str(ent["worker_list"][0].get("work") or "")


def test_prune_closed_focus_items(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    doc = fi.empty_focus()
    doc["strict"] = True
    doc["items"] = {
        "SimonBarnett/bobiverse#1102": {
            "repo": "SimonBarnett/bobiverse",
            "id": "#1102",
            "rank": 1,
            "label": "1",
            "ts": "2026-10-04T00:00:00Z",
        },
        "SimonBarnett/bobiverse#1472": {
            "repo": "SimonBarnett/bobiverse",
            "id": "#1472",
            "rank": 2,
            "label": "2",
            "ts": "2026-10-04T00:00:00Z",
        },
    }
    doc["repos"] = {
        "SimonBarnett/bobiverse": {"priority": 1, "label": "high", "ts": "2026-10-04T00:00:00Z"}
    }
    fi.save_focus(tmp_path, doc)
    n = fi.prune_closed_focus_items(tmp_path, {"simonbarnett/bobiverse#1102"})
    assert n == 1
    left = fi.load_focus(tmp_path)
    assert "SimonBarnett/bobiverse#1102" in left["items"]
    assert "SimonBarnett/bobiverse#1472" not in left["items"]
    assert "SimonBarnett/bobiverse" in left["repos"]


def test_prune_closed_focus_skips_when_open_keys_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    doc = fi.empty_focus()
    doc["items"] = {
        "SimonBarnett/bobiverse#1102": {
            "repo": "SimonBarnett/bobiverse",
            "id": "#1102",
            "rank": 1,
            "label": "1",
            "ts": "2026-10-04T00:00:00Z",
        },
    }
    fi.save_focus(tmp_path, doc)
    assert fi.prune_closed_focus_items(tmp_path, set()) == 0
    assert "SimonBarnett/bobiverse#1102" in fi.load_focus(tmp_path)["items"]


def test_queue_flow_alerts_zero_seat_require_machine_pins(tmp_path):
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    chair.mkdir()
    digest.mkdir()
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
    # Live seats only on ionos host; DEV1 has zero workers.
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
    code, payload = _run_queue_flow(chair, digest)
    # FR #1518: gated-empty is exit 0 with a note (not a false starvation finding).
    assert code == 0, payload
    assert payload["ok"] is True
    joined = " ".join(payload.get("notes") or payload.get("findings") or [])
    assert "require_machine pins only" in joined
    assert "no seats on" in joined
    assert "ce-priority-dev1" in joined
    assert int(payload.get("ungated_offerable_count") or 0) == 0


def test_queue_flow_folds_ionos_pin_to_digest_machine(tmp_path):
    """require_machine=ionos must count seats under win-mpre8vi4u6u (#79 fold)."""
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    chair.mkdir()
    digest.mkdir()
    (chair / "queue.json").write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": [
                    {
                        "repo": "SimonBarnett/bobiverse",
                        "task": "FR",
                        "id": "#999",
                        "require_machine": "ionos",
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
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    code, payload = _run_queue_flow(chair, digest)
    # Pin has seats after fold — still gated (offerable may be 0 for other gates)
    # but must NOT claim "no seats on".
    joined = " ".join(payload.get("findings") or [])
    assert "no seats on" not in joined, payload
