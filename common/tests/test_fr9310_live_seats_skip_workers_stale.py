"""FR #9310: live_seat_nicks must not treat workers_stale last-good restores as live.

After seat drop, bobreport restores workers_last_good into worker_list with
workers_stale=True (FR #8513). Chair then offered to marchhare-8112 while the
machine already had live workers=[] (offer-to-ghost). Auto-offer must ignore
stale restored lists.
"""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim


def _roster(home: Path) -> None:
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["marchhare","flamingo"]}',
        encoding="utf-8",
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None


def test_fr9310_live_seat_nicks_skips_workers_stale_restore(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    doc = bobreport.empty_digest()
    doc["machines"]["marchhare"] = {
        "id": "marchhare",
        "online": True,
        "running": 0,
        "workers": {},
        # Restored last-good ghosts (FR #8513) — TipForm paint only.
        "worker_list": [
            {
                "nick": "marchhare-8112",
                "state": "idle",
                "work": "",
                "updated": "2026-11-23T07:57:00Z",
            }
        ],
        "workers_stale": True,
        "workers_last_good": [
            {
                "nick": "marchhare-8112",
                "state": "idle",
                "work": "",
                "updated": "2026-11-23T07:57:00Z",
            }
        ],
    }
    doc["machines"]["flamingo"] = {
        "id": "flamingo",
        "online": True,
        "workers": {},
        "worker_list": [
            {
                "nick": "flamingo-10116",
                "state": "doing",
                "work": "FR #9310",
                "updated": "2026-11-23T08:04:00Z",
            }
        ],
    }
    bobreport.save_digest(tmp_path, doc)

    live = gitclaim.live_seat_nicks(tmp_path)
    assert "flamingo-10116" in live
    assert "marchhare-8112" not in live


def test_fr9310_live_seat_nicks_keeps_fresh_worker_list(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    doc = bobreport.empty_digest()
    doc["machines"]["marchhare"] = {
        "id": "marchhare",
        "online": True,
        "workers": {},
        "worker_list": [
            {
                "nick": "marchhare-20584",
                "state": "idle",
                "work": "",
                "updated": "2026-11-23T08:00:00Z",
            }
        ],
        # fresh list — not stale
    }
    bobreport.save_digest(tmp_path, doc)
    live = gitclaim.live_seat_nicks(tmp_path)
    assert "marchhare-20584" in live


def test_fr9310_digest_idle_ready_skips_stale_machine(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    doc = bobreport.empty_digest()
    doc["machines"]["marchhare"] = {
        "id": "marchhare",
        "online": True,
        "workers": {},
        "worker_list": [
            {
                "nick": "marchhare-8112",
                "state": "idle",
                "work": "",
                "updated": "2026-11-23T07:57:00Z",
            }
        ],
        "workers_stale": True,
    }
    bobreport.save_digest(tmp_path, doc)
    ready = gitclaim.digest_idle_ready_seats(tmp_path)
    nicks = {str(r.get("nick") or "") for r in ready}
    assert "marchhare-8112" not in nicks
