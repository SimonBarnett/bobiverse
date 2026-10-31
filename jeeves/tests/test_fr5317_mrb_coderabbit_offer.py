"""FR #5317: mocked PR with/without CodeRabbit review gates MRB offer when enabled."""
from __future__ import annotations

from pathlib import Path

import gitclaim
import fuel_chain


def _home(tmp_path: Path) -> Path:
    h = tmp_path / "chair"
    h.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(h),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return h


def _mrb_row(num: str, *, since: float | None = None) -> dict:
    row = {
        "repo": "o/r",
        "task": "MRB",
        "id": f"#{num}",
        "url": f"https://github.com/o/r/pull/{num}",
        "title": f"pr {num}",
        "line": f"MRB #{num}",
        "seq": int(num),
        "state": "open",
    }
    if since is not None:
        row["coderabbit_wait_since"] = since
    return row


def test_offer_skips_unreviewed_until_timeout(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    monkeypatch.setenv("BOB_CODERABBIT_WAIT_MIN", "15")
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [_mrb_row("2", since=1_000.0)],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )

    def no_review(_repo, _num, _head=""):
        return False

    monkeypatch.setattr(fuel_chain, "lookup_coderabbit_reviewed", no_review)
    st, job = gitclaim.offer_focus_top(
        home, "n-1", "#n", now=1_000.0 + 60.0, pr_exists=lambda r, n: True
    )
    assert st == "empty" and job is None

    st2, job2 = gitclaim.offer_focus_top(
        home, "n-1", "#n", now=1_000.0 + 16 * 60.0, pr_exists=lambda r, n: True
    )
    assert st2 == "ok" and job2 is not None
    assert job2.get("coderabbit") == "timeout"
    line = gitclaim.format_assign_line("n-1", job2)
    assert "coderabbit=timeout" in line


def test_offer_when_coderabbit_reviewed(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    home = _home(tmp_path)
    # FR #5394: !bored uses stamped ready (or the shared budget); no extra live GET.
    row = _mrb_row("3", since=1_000.0)
    row["coderabbit"] = "ready"
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [row],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    st, job = gitclaim.offer_focus_top(
        home, "n-1", "#n", now=1_010.0, pr_exists=lambda r, n: True
    )
    assert st == "ok" and job is not None
    assert job.get("coderabbit") == "ready"


def test_offer_unchanged_when_coderabbit_off(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_FUEL_CODERABBIT", raising=False)
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [_mrb_row("4")],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    st, job = gitclaim.offer_focus_top(
        home, "n-1", "#n", now=50.0, pr_exists=lambda r, n: True
    )
    assert st == "ok" and job is not None
    assert "coderabbit=" not in gitclaim.format_assign_line("n-1", job)
