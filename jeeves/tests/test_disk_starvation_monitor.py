# -*- coding: utf-8 -*-
"""disk_starvation monitor: detect disk-low machines from report + dry remediator wiring."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

MON = Path(__file__).resolve().parents[1] / "tools" / "monitor"
sys.path.insert(0, str(MON))

import disk_starvation as ds  # noqa: E402


def test_machine_from_nick():
    assert ds.machine_from_nick("flamingo-17160") == "flamingo"
    assert ds.machine_from_nick("redqueen-11500") == "redqueen"
    assert ds.machine_from_nick("") == ""


def test_detect_disk_machines_from_offer_outcomes():
    doc = {
        "queue": {
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "id": "#9688",
                    "giveup_reason": "worktree-create-failed:disk-low (FR #6240)",
                    "giveup_seats": [],
                    "offer_outcomes": [
                        {
                            "seat": "flamingo-17160",
                            "outcome": "nack",
                            "reason": "worktree-create-failed:disk-low (FR #6240)",
                            "ts": "2026-11-24T15:55:36Z",
                        }
                    ],
                }
            ]
        }
    }
    hits = ds.detect_disk_machines(doc)
    assert "flamingo" in hits
    assert "SimonBarnett/bobiverse#9688" in hits["flamingo"]["jobs"]
    assert "flamingo-17160" in hits["flamingo"]["seats"]


def test_detect_empty_when_no_disk():
    doc = {
        "queue": {
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "id": "#1",
                    "giveup_reason": "holder_bored",
                    "offer_outcomes": [
                        {"seat": "flamingo-1", "outcome": "nack", "reason": "holder_bored"}
                    ],
                }
            ]
        }
    }
    assert ds.detect_disk_machines(doc) == {}


def test_check_fixture_finding_detect_only(monkeypatch, tmp_path):
    fix = tmp_path / "fix.json"
    fix.write_text(
        json.dumps(
            {
                "disk_machines": {
                    "flamingo": {
                        "jobs": ["SimonBarnett/bobiverse#9688"],
                        "seats": ["flamingo-17160"],
                        "reasons": ["disk-low"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("JEEVES_DISK_STARVATION_FIXTURE", str(fix))
    monkeypatch.setenv("BOB_DISK_STARVATION_AUTO", "0")
    monkeypatch.setenv("BOB_DISK_STARVATION_FILE", "0")
    payload, code = ds.check(SimpleNamespace(dry_run=False))
    assert code == ds.EXIT_FINDING
    assert payload["ok"] is False
    assert "flamingo" in payload["machines"]
    assert payload["auto"] is False


def test_check_dry_run_ok():
    # run_check --dry-run path
    rc = ds.main(["--dry-run"])
    assert rc == 0


def test_mrb9700_remediator_skips_bridge_leaves_with_local_work():
    """Hostile MRB #9700: orphan bob-bridge rmdir must gate on git local work."""
    rem = (
        Path(__file__).resolve().parents[2]
        / "common"
        / "scripts"
        / "Invoke-BobiverseDiskStarvationRemediate.ps1"
    )
    text = rem.read_text(encoding="utf-8-sig")
    assert "Test-BridgeLeafHasLocalWork" in text
    assert "orphan_bob_bridge_skip_local_work" in text
    assert "status --porcelain" in text
