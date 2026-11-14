"""FR #7334: recycle the least-touched idle author when MRB has no reviewer."""
from __future__ import annotations

import gitclaim
import registered_machines


NOW = 1_800_000_000.0
SEATS = ("redqueen-8380", "flamingo-12296", "marchhare-31172")
COUNTS = {
    "redqueen-8380": 4,
    "flamingo-12296": 1,
    "marchhare-31172": 2,
}


def _row(since: float) -> dict:
    return {
        "task": "MRB",
        "repo": "SimonBarnett/bobiverse",
        "id": "#7311",
        "url": "https://github.com/SimonBarnett/bobiverse/pull/7311",
        "title": "FR #7300",
        "author_seats": ",".join(SEATS),
        "author_commit_counts": dict(COUNTS),
        "no_eligible_since": since,
    }


def _write(home, row, accepted=None):
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": list(accepted or []), "done": []},
    )


def _ready(home, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    registered_machines.save_registered(home, {"redqueen", "flamingo", "marchhare"})


def _outbox(home) -> str:
    path = home / "chair-outbox.txt"
    if not path.is_file():
        import bobreport
        path = bobreport.fleet_digest_home(home) / "chair-outbox.txt"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def test_fr7334_three_idle_authors_one_recycle_and_fresh_offer(tmp_path, monkeypatch):
    _ready(tmp_path, monkeypatch)
    monkeypatch.setattr(gitclaim, "mrb_has_eligible_reviewer", lambda *a, **k: False)
    row = _row(NOW - 301)
    _write(tmp_path, row)
    install = tmp_path / "install"
    install.mkdir()
    lines = gitclaim.maybe_recycle_stuck_no_eligible_reviewer(
        tmp_path,
        idle=set(SEATS),
        live=set(SEATS),
        now=NOW,
        accepted=[],
        install_root=install,
    )
    assert sum("recycleseat=flamingo-12296" in x for x in lines) == 1, lines
    text = _outbox(tmp_path)
    assert text.count("!recycleseat flamingo-12296") == 1
    assert "PRIVMSG #bobiverse :recycled flamingo-12296" in text
    fresh = "flamingo-1"
    live = set(SEATS) | {fresh}
    assert gitclaim.review_blocked_for_author(row, "flamingo-12296", live) is True
    assert gitclaim.review_blocked_for_author(row, fresh, live) is False
    assert gitclaim.mrb_offer_nick(row, [fresh, *SEATS], live) == fresh


def test_fr7334_busy_author_is_not_recycled(tmp_path, monkeypatch):
    _ready(tmp_path, monkeypatch)
    monkeypatch.setattr(gitclaim, "mrb_has_eligible_reviewer", lambda *a, **k: False)
    row = _row(NOW - 600)
    accepted = [{"task": "FR", "accepted_by": "flamingo-12296", "repo": "SimonBarnett/bobiverse", "id": "#1"}]
    _write(tmp_path, row, accepted)
    install = tmp_path / "install"
    install.mkdir()
    lines = gitclaim.maybe_recycle_stuck_no_eligible_reviewer(
        tmp_path,
        idle=set(SEATS),
        live=set(SEATS),
        now=NOW,
        accepted=accepted,
        install_root=install,
    )
    assert sum("recycleseat=marchhare-31172" in x for x in lines) == 1, lines
    assert "flamingo-12296" not in " ".join(lines)


def test_fr7334_under_five_minutes_does_not_recycle(tmp_path, monkeypatch):
    _ready(tmp_path, monkeypatch)
    monkeypatch.setattr(gitclaim, "mrb_has_eligible_reviewer", lambda *a, **k: False)
    _write(tmp_path, _row(NOW - 60))
    install = tmp_path / "install"
    install.mkdir()
    lines = gitclaim.maybe_recycle_stuck_no_eligible_reviewer(
        tmp_path,
        idle=set(SEATS),
        live=set(SEATS),
        now=NOW,
        accepted=[],
        install_root=install,
    )
    assert lines == []
    assert "!recycleseat" not in _outbox(tmp_path)


def test_fr7334_second_scan_does_not_recycle_another_author(tmp_path, monkeypatch):
    """After one recycle, wait another 5 minutes; do not drain the fleet."""
    _ready(tmp_path, monkeypatch)
    monkeypatch.setattr(gitclaim, "mrb_has_eligible_reviewer", lambda *a, **k: False)
    row = _row(NOW - 301)
    _write(tmp_path, row)
    install = tmp_path / "install"
    install.mkdir()
    first = gitclaim.maybe_recycle_stuck_no_eligible_reviewer(
        tmp_path,
        idle=set(SEATS),
        live=set(SEATS),
        now=NOW,
        accepted=[],
        install_root=install,
    )
    assert sum("recycleseat=flamingo-12296" in x for x in first) == 1, first
    second = gitclaim.maybe_recycle_stuck_no_eligible_reviewer(
        tmp_path,
        idle=set(SEATS),
        live=set(SEATS),
        now=NOW + 60.0,
        accepted=[],
        install_root=install,
    )
    assert second == [], second
    assert _outbox(tmp_path).count("!recycleseat") == 1


def test_fr7334_chair_health_wires_helper():
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "common" / "scripts" / "chair_health.py"
    text = src.read_text(encoding="utf-8")
    assert "maybe_recycle_stuck_no_eligible_reviewer" in text
    assert "FR #7334" in text
