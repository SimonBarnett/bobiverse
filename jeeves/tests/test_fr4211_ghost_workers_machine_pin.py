"""FR #4211: ghost legacy workers must not block same-machine reviews; prose ionos is not a pin."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import registered_machines


def _roster(home: Path, machines=("marchhare", "win-mpre8vi4u6u", "flamingo")) -> None:
    registered_machines.save_registered(home, set(machines))
    bobreport._SEAT_ROSTER_CACHE["key"] = None


def test_infer_require_machine_mere_ionos_mention_does_not_pin():
    """FR text that only mentions ionos in prose must not pin the derived MRB."""
    assert (
        gitclaim.infer_require_machine(
            title="bob-worker: ack-miss HUNG on out-of-fuel seat",
            body=(
                "On ionos (WIN-MPRE8VI4U6U, worker bob-worker-4243bc16831b.exe), "
                "both seats detected out-of-fuel and posted GIVEUP."
            ),
            labels=("bug",),
        )
        == ""
    )
    assert (
        gitclaim.infer_require_machine(
            title="runs on ionos sometimes",
            body="evidence gathered on an ionos box; fix is fleet-wide",
            labels=("bug",),
        )
        == ""
    )


def test_infer_require_machine_dedicated_pin_line_and_needs_label_still_pin():
    assert (
        gitclaim.infer_require_machine(
            title="chair recycle",
            body="require_machine: ionos\n\nPlease bounce ircJeeves after the patch.",
            labels=("bug",),
        )
        == "ionos"
    )
    assert (
        gitclaim.infer_require_machine(
            title="ops",
            body="require_machine = ce-priority-dev1\n",
            labels=("bug",),
        )
        == "ce-priority-dev1"
    )
    assert (
        gitclaim.infer_require_machine(
            title="x",
            body="",
            labels=("needs-ionos",),
        )
        == "ionos"
    )
    assert (
        gitclaim.infer_require_machine(
            title="x",
            body="",
            labels=("machine:marchhare",),
        )
        == "marchhare"
    )


def test_ghost_legacy_workers_do_not_block_same_machine_uat_sibling(
    tmp_path, monkeypatch
):
    """Empty worker_list + stale pid workers on another machine must not UAT sibling-block.

    MRB self-exclusion is exact-seat only (FR #2604); UAT still uses the sibling rule
    (FR #227 / #1407). Ghosts must not count as the viable other-machine seat.
    """
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("BOB_MACHINE_ID", "marchhare")
    _roster(tmp_path)

    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [
        {
            "nick": "marchhare-28716",
            "state": "idle",
            "work": "",
            "updated": "2026-10-14T12:00:00Z",
        },
        {
            "nick": "marchhare-43484",
            "state": "idle",
            "work": "",
            "updated": "2026-10-14T12:00:00Z",
        },
    ]
    digest["machines"]["marchhare"]["workers"] = {}
    digest["machines"]["win-mpre8vi4u6u"] = bobreport._empty_machine("win-mpre8vi4u6u")
    digest["machines"]["win-mpre8vi4u6u"]["worker_list"] = []
    digest["machines"]["win-mpre8vi4u6u"]["workers"] = {
        "884": {
            "pid": "884",
            "nick": "w-io-884",
            "state": "idle",
            "working_on": "",
            "updated": "2026-10-01T00:00:00Z",
        }
    }
    bobreport.save_digest(tmp_path, digest)

    live = gitclaim.live_seat_nicks(tmp_path)
    assert "marchhare-28716" in live
    assert "marchhare-43484" in live
    assert "win-mpre8vi4u6u-884" not in live
    assert "w-io-884" not in live

    mrb = {
        "repo": "SimonBarnett/bobiverse",
        "task": "MRB",
        "id": "#4193",
        "url": "https://github.com/SimonBarnett/bobiverse/pull/4193",
        "author_seat": "marchhare-43484",
        "implementer_seat": "marchhare-43484",
        "event": "pull_request",
    }
    assert gitclaim.review_blocked_for_author(mrb, "marchhare-43484", live) is True
    assert gitclaim.review_blocked_for_author(mrb, "marchhare-28716", live) is False

    uat = {
        "repo": "SimonBarnett/bobiverse",
        "task": "UAT",
        "id": "#0",
        "repo_uat": True,
        "author_seat": "marchhare-43484",
        "implementer_seat": "marchhare-43484",
        "mrb_author_seat": "marchhare-43484",
    }
    assert gitclaim.review_blocked_for_author(uat, "marchhare-43484", live) is True
    assert gitclaim.review_blocked_for_author(uat, "marchhare-28716", live) is False


def test_live_legacy_workers_with_fresh_heartbeat_still_count(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("BOB_MACHINE_ID", "marchhare")
    _roster(tmp_path)
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = []
    digest["machines"]["flamingo"]["workers"] = {
        "9": {
            "pid": "9",
            "nick": "flamingo-9",
            "state": "idle",
            "updated": "2099-01-01T00:00:00Z",
        }
    }
    bobreport.save_digest(tmp_path, digest)
    live = gitclaim.live_seat_nicks(tmp_path)
    assert "flamingo-9" in live


def test_live_legacy_workers_local_dead_pid_skipped(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("BOB_MACHINE_ID", "win-mpre8vi4u6u")
    _roster(tmp_path)
    digest = bobreport.empty_digest()
    digest["machines"]["win-mpre8vi4u6u"] = bobreport._empty_machine("win-mpre8vi4u6u")
    digest["machines"]["win-mpre8vi4u6u"]["worker_list"] = []
    digest["machines"]["win-mpre8vi4u6u"]["workers"] = {
        "884": {"pid": "884", "nick": "w-io-884", "state": "idle"},
        "11692": {"pid": "11692", "nick": "win-mpre8vi4u6u-11692", "state": "idle"},
    }
    bobreport.save_digest(tmp_path, digest)

    def _alive(pid: int) -> bool:
        return int(pid) == 11692

    monkeypatch.setattr(bobreport, "_pid_alive", _alive)
    live = gitclaim.live_seat_nicks(tmp_path)
    assert "win-mpre8vi4u6u-11692" in live
    assert "win-mpre8vi4u6u-884" not in live


def test_real_other_machine_live_seat_still_blocks_uat_sibling(tmp_path, monkeypatch):
    """No regression of FR #227 / #1407: a real live other-machine seat still UAT sibling-blocks."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("BOB_MACHINE_ID", "marchhare")
    _roster(tmp_path)
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [
        {
            "nick": "marchhare-1",
            "state": "idle",
            "work": "",
            "updated": "2026-10-14T12:00:00Z",
        },
        {
            "nick": "marchhare-2",
            "state": "idle",
            "work": "",
            "updated": "2026-10-14T12:00:00Z",
        },
    ]
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {
            "nick": "flamingo-9",
            "state": "idle",
            "work": "",
            "updated": "2026-10-14T12:00:00Z",
        }
    ]
    bobreport.save_digest(tmp_path, digest)
    live = gitclaim.live_seat_nicks(tmp_path)
    uat = {
        "repo": "SimonBarnett/bobiverse",
        "task": "UAT",
        "id": "#0",
        "repo_uat": True,
        "author_seat": "marchhare-1",
        "implementer_seat": "marchhare-1",
    }
    assert gitclaim.review_blocked_for_author(uat, "marchhare-2", live) is True
    assert gitclaim.review_blocked_for_author(uat, "flamingo-9", live) is False
