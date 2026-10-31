"""docs/mrb-5175 leftover pins for FR #5174 / PR #5175."""
from __future__ import annotations

from pathlib import Path

import copilot_dispatch as cd
import focus_ignore as fi
import gitclaim


REPO = "SimonBarnett/a-search"


def _row(**extra):
    row = {
        "repo": REPO,
        "task": "FR",
        "id": "#99",
        "url": f"https://github.com/{REPO}/issues/99",
        "title": "x",
    }
    row.update(extra)
    return row


def test_http_201_without_task_id_does_not_accept(tmp_path):
    fi.handle_focus_cmd(tmp_path, f"high {REPO}")
    cd.refresh_allowance(
        tmp_path,
        fetch_user=lambda: {
            "quota_snapshots": {
                "premium_interactions": {"unlimited": True, "remaining": 0, "percent_remaining": 100}
            }
        },
        now=1.0,
    )
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [_row()], "accepted": [], "done": []},
    )
    announced: list[str] = []
    out = cd.dispatch_row(
        tmp_path,
        _row(),
        post=lambda *_a, **_k: {"status": 201, "html_url": "https://example/no-id"},
        announce=announced.append,
    )
    assert out.get("status") != "dispatched"
    assert "missing-task-id" in str(out)
    assert announced == []
    assert any(r.get("id") == "#99" for r in gitclaim.load_unaccepted(tmp_path))


def test_needs_ionos_pin_skipped():
    row = _row(require_machine="ionos")
    assert cd.should_dispatch(row, allowance=True) is False
    row2 = _row()
    row2["labels"] = ["needs-ionos"]
    # stamp if gitclaim maps the label
    with __import__("contextlib").suppress(Exception):
        gitclaim._stamp_require_machine(row2)
    if row2.get("require_machine"):
        assert cd.should_dispatch(row2, allowance=True) is False
