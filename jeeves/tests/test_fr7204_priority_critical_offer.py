"""FR #7204: Jeeves offers priority/critical issues first (oldest among them)."""
from __future__ import annotations

from pathlib import Path

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines
import pytest


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"marchhare", "flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["workers"] = {"1": {"state": "idle"}}
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["workers"] = {"9": {"state": "idle"}}
    bobreport.save_digest(tmp_path, digest)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return tmp_path


def _row(repo: str, task: str, num: int, **kw) -> dict:
    r = {
        "repo": repo,
        "task": task,
        "id": f"#{num}",
        "seq": num,
        "ts": kw.pop("ts", f"2026-11-14T10:00:{num:02d}Z"),
        "line": f"{task} {repo}#{num}",
        "url": f"https://github.com/{repo}/issues/{num}",
        "title": f"{task} {num}",
        "state": "open",
        "labels": list(kw.pop("labels", [])),
    }
    r.update(kw)
    return r


def _queue(home: Path, rows: list[dict]) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": rows, "accepted": [], "done": [], "workers": {}},
    )


def test_critical_before_normal_and_oldest_critical_first(home: Path):
    repo = "SimonBarnett/bobiverse"
    _queue(
        home,
        [
            _row(repo, "FR", 9, ts="2026-11-14T12:00:00Z"),
            _row(
                repo,
                "FR",
                3,
                ts="2026-11-14T11:00:00Z",
                labels=["priority/critical", "bug"],
            ),
            _row(
                repo,
                "MRB",
                1,
                ts="2026-11-14T10:00:00Z",
                labels=["priority/critical"],
                url="https://github.com/SimonBarnett/bobiverse/pull/1",
            ),
            _row(repo, "FR", 8, ts="2026-11-14T09:00:00Z"),
        ],
    )
    ids = [r["id"] for r in gitclaim.ordered_unaccepted(home)]
    assert ids[:2] == ["#1", "#3"], ids
    assert ids[2:] == ["#8", "#9"] or set(ids[2:]) == {"#8", "#9"}


def test_ineligible_critical_skipped_does_not_block(home: Path):
    repo = "Acme/widget"
    _queue(
        home,
        [
            _row(
                repo,
                "FR",
                100,
                labels=["priority/critical"],
                require_machine="ionos",
            ),
            _row(repo, "FR", 101),
        ],
    )
    st, job = gitclaim.offer_focus_top(home, "marchhare-1", "#marchhare")
    assert st == "ok" and job is not None
    assert job["id"] == "#101"


def test_adding_critical_label_after_queue_changes_next_offer(home: Path):
    repo = "SimonBarnett/bobiverse"
    _queue(
        home,
        [
            _row(repo, "FR", 5, ts="2026-11-14T08:00:00Z"),
            _row(repo, "FR", 50, ts="2026-11-14T12:00:00Z"),
        ],
    )
    first = [r["id"] for r in gitclaim.ordered_unaccepted(home)]
    assert first[0] == "#5"
    rows = gitclaim.load_unaccepted(home)
    for r in rows:
        if r["id"] == "#50":
            r["labels"] = ["priority/critical"]
    _queue(home, rows)
    later = [r["id"] for r in gitclaim.ordered_unaccepted(home)]
    assert later[0] == "#50"


def test_offer_order_stable_for_equal_ts(home: Path):
    repo = "SimonBarnett/bobiverse"
    ts = "2026-11-14T10:00:00Z"
    _queue(
        home,
        [
            _row(repo, "FR", 20, ts=ts, labels=["priority/critical"]),
            _row(repo, "FR", 10, ts=ts, labels=["priority/critical"]),
        ],
    )
    a = [r["id"] for r in gitclaim.ordered_unaccepted(home)]
    b = [r["id"] for r in gitclaim.ordered_unaccepted(home)]
    assert a == b == ["#10", "#20"]


def test_list_line_marks_critical():
    row = _row("SimonBarnett/bobiverse", "FR", 7204, labels=["priority/critical"])
    line = gitclaim.format_list_line(1, row, now=0)
    assert "[critical]" in line
    assert "7204" in line
    plain = gitclaim.format_list_line(1, _row("SimonBarnett/bobiverse", "FR", 1), now=0)
    assert "[critical]" not in plain
