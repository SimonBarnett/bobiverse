# -*- coding: utf-8 -*-
"""FR #9838: copilot_dispatch skips children of held fr-digest (parity with #9821).

Fail-when: #9803 CCA-dispatched while parent #9795 is held.
"""
from __future__ import annotations

from pathlib import Path

import copilot_dispatch as cd
import focus_ignore as fi
import gitclaim
import pytest

REPO = "SimonBarnett/bobiverse"


def _row(num: int, **kw) -> dict:
    r = {
        "repo": REPO,
        "task": "FR",
        "id": f"#{num}",
        "seq": num,
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


@pytest.fixture
def home(tmp_path: Path) -> Path:
    _write(tmp_path, [])
    fi.handle_focus_cmd(tmp_path, f"high {REPO}")
    cd.set_allowance(tmp_path, remaining=10)
    return tmp_path


def test_fr9838_held_digest_child_should_not_dispatch(home: Path):
    """Fail-when: #9803 under held #9795 must not CCA."""
    digest = _row(
        9795,
        title="Digest: .NET fuel",
        labels=["feature-request", "fr-digest", "hold", "digest"],
        body="Kind: fr-digest\n",
    )
    child = _row(
        9803,
        title="FR-D: fuel cache",
        body="Depends-on: #9795\nImplement fuel cache.\n",
    )
    free = _row(9999, body="Depends-on: (none)\n")
    _write(home, [digest, child, free])

    assert gitclaim.depends_gate_reason(child, gitclaim.load_queue(home)) == (
        gitclaim.DEPENDS_HELD_REASON
    )
    assert cd.held_digest_cca_skip_reason(home, child) == gitclaim.DEPENDS_HELD_REASON
    assert cd.should_dispatch(child, allowance=True, home=home) is False

    posts: list = []

    def _post(path: str, body: dict) -> dict:
        posts.append((path, body))
        return {"status": 201, "id": "task-should-not"}

    out = cd.dispatch_row(home, child, post=_post)
    assert out.get("status") == "skip"
    assert posts == []


def test_fr9838_unheld_digest_child_may_dispatch(home: Path):
    digest = _row(
        9795,
        title="Digest: .NET fuel",
        labels=["feature-request", "fr-digest", "digest"],
        body="Kind: fr-digest\n",
    )
    child = _row(
        9803,
        title="FR-D: fuel cache",
        body="Depends-on: #9795\nImplement fuel cache.\n",
    )
    _write(home, [digest, child])

    assert cd.held_digest_cca_skip_reason(home, child) is None
    assert cd.should_dispatch(child, allowance=True, home=home) is True


def test_fr9838_tick_skips_held_child_dispatches_free(home: Path):
    digest = _row(
        9795,
        title="Digest: .NET fuel",
        labels=["fr-digest", "hold", "digest"],
        body="Kind: fr-digest\n",
    )
    child = _row(9803, body="Depends-on: #9795\n", title="held child")
    free = _row(9999, body="Depends-on: (none)\n", title="free FR")
    _write(home, [digest, child, free])

    posted_ids: list[str] = []

    def _post(path: str, body: dict) -> dict:
        # prompt cites the issue number
        prompt = str((body or {}).get("prompt") or "")
        posted_ids.append(prompt)
        return {
            "status": 201,
            "id": f"task-{len(posted_ids)}",
            "html_url": f"https://github.com/orgs/x/tasks/{len(posted_ids)}",
        }

    out = cd.tick(home, post=_post, announce=lambda *_a, **_k: None)
    assert out.get("dispatched", 0) >= 1
    blob = "\n".join(posted_ids)
    assert "9803" not in blob
    assert "9999" in blob or "#9999" in blob


def test_fr9838_shares_bob_g1_marker():
    import fr_digest_gate as fdg

    assert "held" in fdg.bob_g1_skip_held_digest().lower()
    src = Path(cd.__file__).read_text(encoding="utf-8")
    assert "held_digest_cca_skip_reason" in src
    assert "depends_gate_reason" in src
