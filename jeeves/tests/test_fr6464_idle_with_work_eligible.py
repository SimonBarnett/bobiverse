"""FR #6464: idle-with-work only when idle seats can take the waiting work."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import bobreport
import focus_ignore
import gitclaim
import registered_machines
import stall_detectors as sd


def _old_ts(now: float, age_s: float = 3600.0) -> str:
    return datetime.fromtimestamp(now - age_s, tz=timezone.utc).isoformat()


def _fr_row(*, repo, num, ts, require_machine="", title="plain"):
    return {
        "task": "FR",
        "repo": repo,
        "id": f"#{num}",
        "ident": str(num),
        "url": f"https://github.com/{repo}/issues/{num}",
        "title": title,
        "body": "",
        "ts": ts,
        "require_machine": require_machine,
        "labels": ["feature-request"],
        "event": "issues",
        "line": "FR",
    }


def test_fr6464_machine_mismatch_idle_is_silent():
    """Pinned to another machine while this shop is idle must not file idle-with-work.

    Live class of #6464 was ce-priority#16/#17 vs flamingo; after FR #6407, DEV1
    stamps clear in row_require_machine, so pin a live machine (redqueen) here.
    """
    now = 1_700_000_000.0
    snap = {
        "now": now,
        "idle": ["flamingo-68408"],
        "unaccepted": [
            _fr_row(
                repo="SimonBarnett/a-search",
                num=9999,
                ts=_old_ts(now, 2787914),
                require_machine="redqueen",
                title="needs redqueen",
            ),
        ],
    }
    assert sd.detect_idle_with_work(snap) == []


def test_fr6464_unpinned_old_work_still_fires_without_home():
    now = 1_700_000_000.0
    snap = {
        "now": now,
        "idle": ["flamingo-68408"],
        "unaccepted": [
            _fr_row(
                repo="SimonBarnett/ce-priority",
                num=16,
                ts=_old_ts(now, 3600),
                require_machine="any",
            )
        ],
    }
    found = sd.detect_idle_with_work(snap)
    assert len(found) == 1
    assert found[0]["id"] == sd.IDLE_WITH_WORK_ID


def _home(tmp_path: Path, monkeypatch, machines=None):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    mids = set(machines or {"flamingo"})
    registered_machines.save_registered(tmp_path, mids)
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    for mid in mids:
        digest["machines"][mid] = bobreport._empty_machine(mid)
        digest["machines"][mid]["worker_list"] = [
            {"nick": f"{mid}-1", "state": "idle"},
        ]
    bobreport.save_digest(tmp_path, digest)
    return tmp_path


def test_fr6464_home_offerable_zero_silent(tmp_path: Path, monkeypatch):
    """When chair home is in the snap, offerable=0 for idle seats suppresses the stall."""
    now = 1_700_000_000.0
    home = _home(tmp_path, monkeypatch, {"flamingo", "redqueen"})
    focus_ignore.handle_focus_cmd(home, "high SimonBarnett/a-search")
    row = _fr_row(
        repo="SimonBarnett/a-search",
        num=9999,
        ts=_old_ts(now, 3600),
        require_machine="redqueen",
        title="redqueen only",
    )
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    snap = {
        "home": home,
        "now": now,
        "idle": ["flamingo-1"],
        "unaccepted": list(gitclaim.load_unaccepted(home)),
    }
    summary = gitclaim.summarize_empty_offer(home, "flamingo-1")
    assert int(summary.get("offerable") or 0) == 0
    assert sd.detect_idle_with_work(snap) == []


def test_fr6464_home_offerable_positive_fires(tmp_path: Path, monkeypatch):
    now = 1_700_000_000.0
    home = _home(tmp_path, monkeypatch, {"flamingo"})
    focus_ignore.handle_focus_cmd(home, "high SimonBarnett/bobiverse")
    row = _fr_row(
        repo="SimonBarnett/bobiverse",
        num=9999,
        ts=_old_ts(now, 3600),
        require_machine="any",
        title="ungated work",
    )
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    snap = {
        "home": home,
        "now": now,
        "idle": ["flamingo-1"],
        "unaccepted": list(gitclaim.load_unaccepted(home)),
    }
    summary = gitclaim.summarize_empty_offer(home, "flamingo-1")
    assert int(summary.get("offerable") or 0) >= 1
    found = sd.detect_idle_with_work(snap)
    assert len(found) == 1
