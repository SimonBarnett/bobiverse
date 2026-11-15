"""FR #7574: recycle only a live seat that would be eligible."""
from __future__ import annotations

import gitclaim
import registered_machines

NOW = 1_800_000_000.0


def _row(**extra) -> dict:
    row = {
        "task": "MRB",
        "repo": "acme/widgets",
        "id": "#40",
        "url": "https://github.com/acme/widgets/pull/40",
        "author_seats": "boxa-1,boxa-2",
        "no_eligible_since": NOW - 400,
    }
    row.update(extra)
    return row


def _ready(home, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    registered_machines.save_registered(home, {"boxa", "boxb"})
    monkeypatch.setattr(gitclaim, "mrb_has_eligible_reviewer", lambda *a, **k: False)


def _run(home, monkeypatch, *, idle, live, row, ledger=None):
    _ready(home, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    install = home / "install"
    install.mkdir()
    return gitclaim.maybe_recycle_stuck_no_eligible_reviewer(
        home,
        idle=set(idle),
        live=set(live),
        now=NOW,
        accepted=[],
        install_root=install,
        ledger=ledger or {"v": 1, "giveup": {}},
    )


def test_fr7574_stale_author_and_live_implementer_recycle_nothing(tmp_path, monkeypatch):
    lines = _run(
        tmp_path,
        monkeypatch,
        idle={"boxa-1", "boxa-2"},
        live={"boxa-2"},
        row=_row(),
    )
    assert not any("recycleseat=" in x for x in lines), lines
    assert lines == ["no_eligible_reviewer acme/widgets#40"]
    again = gitclaim.maybe_recycle_stuck_no_eligible_reviewer(
        tmp_path,
        idle={"boxa-1", "boxa-2"},
        live={"boxa-2"},
        now=NOW + 30,
        accepted=[],
        install_root=tmp_path / "install",
        ledger={"v": 1, "giveup": {}},
    )
    assert again == []


def test_fr7574_live_non_author_is_chosen(tmp_path, monkeypatch):
    lines = _run(
        tmp_path,
        monkeypatch,
        idle={"boxa-1", "boxb-3"},
        live={"boxa-1", "boxb-3"},
        row=_row(),
    )
    assert len(lines) == 1 and lines[0].startswith("no-eligible-reviewer recycleseat=boxb-3 "), lines
    assert "boxa-1" not in lines[0]


def test_fr7574_live_non_author_giveup_is_skipped(tmp_path, monkeypatch):
    lines = _run(
        tmp_path,
        monkeypatch,
        idle={"boxb-3"},
        live={"boxb-3"},
        row=_row(giveup_seats="boxb-3"),
        ledger={"v": 1, "giveup": {"acme/widgets#40": {"boxb-3": ["MRB"]}}},
    )
    assert not any("recycleseat=" in x for x in lines), lines
    assert lines == ["no_eligible_reviewer acme/widgets#40"]
