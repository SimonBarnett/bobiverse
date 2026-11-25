# -*- coding: utf-8 -*-
"""FR #9833: optional Jeeves-build dispatch lock (offer allowlist).

Fail-when: lock on and tray FR #9750 is offered.
Lock on + tip MRB with jeeves/+common/ paths ⇒ offered; allowlisted gate FR offered.
"""
from __future__ import annotations

import sys
from pathlib import Path

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "common" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import dispatch_lock as dl  # noqa: E402

REPO = "SimonBarnett/bobiverse"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"marchhare", "flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [
        {
            "nick": "marchhare-35600",
            "state": "idle",
            "kind": "grok",
            "start_model": "grok-4",
            "configured_model": "grok-4",
            "updated": "2026-11-24T12:00:00Z",
        }
    ]
    bobreport.save_digest(tmp_path, digest)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return tmp_path


def _row(num: int, seq: int, **kw) -> dict:
    r = {
        "repo": REPO,
        "task": "FR",
        "id": f"#{num}",
        "seq": seq,
        "ts": f"2026-11-24T10:00:{num % 60:02d}Z",
        "line": f"FR {REPO}#{num}",
        "url": f"https://github.com/{REPO}/issues/{num}",
        "title": f"FR {num}",
        "state": "open",
        "body": "Depends-on: (none)\n",
        "event": "issues",
        "labels": [],
    }
    r.update(kw)
    return r


def _write(home: Path, unaccepted: list[dict]) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": unaccepted,
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )


def test_fr9833_default_off(home: Path):
    assert dl.is_on(home) is False
    assert dl.row_blocked_reason(home, _row(9750, 1)) is None
    assert "off" in dl.status_line(home)


def test_fr9833_focus_cmd_on_off(home: Path):
    lines = fi.handle_focus_cmd(home, "build-jeeves on")
    assert any("on" in ln for ln in lines)
    assert dl.is_on(home) is True
    assert (home / dl.LOCK_FILE).is_file()

    bare = fi.handle_focus_cmd(home, "build-jeeves")
    assert any("on" in ln for ln in bare)

    focus_lines = fi.format_focus_lines(home)
    assert any("dispatch-lock" in ln and "on" in ln for ln in focus_lines)

    off = fi.handle_focus_cmd(home, "build-jeeves off")
    assert any("off" in ln for ln in off)
    assert dl.is_on(home) is False


def test_fr9833_lock_blocks_tray_fr_allows_gate_and_tip_mrb(home: Path):
    """Fail-when: #9750 offered while lock on; tip jeeves MRB + gate FR admitted."""
    dl.set_build_jeeves(home, True)

    tray = _row(9750, 1, title="tray TipForm restore")
    gate = _row(9821, 2, title="held fr-digest gate")
    tip_mrb = _row(
        9772,
        3,
        task="MRB",
        title="jeeves tip",
        url=f"https://github.com/{REPO}/pull/9772",
        line=f"MRB {REPO}#9772",
        event="pull_request",
        changed_files=["jeeves/tools/monitor/x.py", "common/scripts/y.py"],
    )
    path_mrb = _row(
        9900,
        4,
        task="MRB",
        title="bob path tip",
        url=f"https://github.com/{REPO}/pull/9900",
        line=f"MRB {REPO}#9900",
        event="pull_request",
        changed_files=["bob/worker/Agents.md"],
    )
    lesson = _row(
        9910,
        5,
        title="lesson(harvest): something",
        labels=["harvest-lesson"],
    )
    prefix_fr = _row(9785, 6, title="978x family gate")

    assert dl.row_blocked_reason(home, tray) == "dispatch-lock:fr"
    assert dl.row_blocked_reason(home, gate) is None
    assert dl.row_blocked_reason(home, tip_mrb) is None
    assert dl.row_blocked_reason(home, path_mrb) == "dispatch-lock:path"
    assert dl.row_blocked_reason(home, lesson) == "dispatch-lock:harvest-lesson"
    assert dl.row_blocked_reason(home, prefix_fr) is None

    kept = fi.sort_unaccepted_rows(
        home, [tray, gate, tip_mrb, path_mrb, lesson, prefix_fr]
    )
    ids = {r["id"] for r in kept}
    assert "#9750" not in ids
    assert "#9900" not in ids
    assert "#9910" not in ids
    assert "#9821" in ids
    assert "#9772" in ids
    assert "#9785" in ids


def test_fr9833_offer_skips_9750_offers_tip_mrb(home: Path):
    """Lock on: !bored must not offer tray #9750; tip MRB with jeeves paths wins.

    Also pins FR #9833 vs FR #8138: mrb_yields_to_older_fr must not yield to a
    lock-blocked older FR still sitting in raw unaccepted.
    """
    me = "marchhare-35600"
    dl.set_build_jeeves(home, True)
    tray = _row(9750, 1, title="tray child")
    tip_mrb = _row(
        9772,
        2,
        task="MRB",
        title="jeeves+common tip",
        url=f"https://github.com/{REPO}/pull/9772",
        line=f"MRB {REPO}#9772",
        event="pull_request",
        changed_files=["jeeves/docs/x.md", "common/scripts/dispatch_lock.py"],
        coderabbit="off",
        review="full",
    )
    _write(home, [tray, tip_mrb])
    fi.handle_focus_cmd(home, REPO)

    assert gitclaim.mrb_yields_to_older_fr(
        home, tip_mrb, me, 0.0, {me}, {}, set(), [tray, tip_mrb]
    ) is False

    st, job = gitclaim.offer_focus_top(home, me, "#marchhare")
    assert st == "ok" and job is not None
    assert job["id"] == "#9772"
    assert job["task"] == "MRB"


def test_fr9833_offer_fail_when_only_9750(home: Path):
    """Fail-when: lock on and only #9750 queued ⇒ empty offer (never that FR)."""
    me = "marchhare-35600"
    dl.set_build_jeeves(home, True)
    _write(home, [_row(9750, 1, title="tray only")])
    fi.handle_focus_cmd(home, REPO)

    st, job = gitclaim.offer_focus_top(home, me, "#marchhare")
    assert job is None or str(job.get("id") or "") != "#9750"
    # Prefer empty / no-offer over wrong assign
    if st == "ok" and job is not None:
        pytest.fail(f"must not offer #9750 under build-jeeves lock; got {job}")


def test_fr9833_lock_off_admits_9750(home: Path):
    """Default / off: tray FR is not blocked by dispatch lock."""
    me = "marchhare-35600"
    assert dl.is_on(home) is False
    _write(home, [_row(9750, 1, title="tray")])
    fi.handle_focus_cmd(home, REPO)
    st, job = gitclaim.offer_focus_top(home, me, "#marchhare")
    assert st == "ok" and job is not None
    assert job["id"] == "#9750"

def test_assign_row_refuses_when_lock_blocks(tmp_path, monkeypatch):
    """FR #9833: !assign must refuse lock-blocked rows (same as !bored)."""
    import bobreport
    import registered_machines

    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"ionos"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    dl.set_build_jeeves(tmp_path, True)
    rows = [
        {
            "task": "FR",
            "id": "#9750",
            "repo": "SimonBarnett/bobiverse",
            "url": "https://github.com/SimonBarnett/bobiverse/issues/9750",
            "seq": 1,
            "ts": "2026-01-01T00:00:01Z",
            "line": "x",
        }
    ]
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": rows, "accepted": []},
    )
    # Presence unknown (empty worker_list) must not block assign in tests.
    st, why = gitclaim.assign_row(
        tmp_path, "ionos-1", "SimonBarnett/bobiverse", "FR", "9750"
    )
    assert st == "refused"
    assert "build-jeeves" in str(why).lower() or "lock" in str(why).lower()
