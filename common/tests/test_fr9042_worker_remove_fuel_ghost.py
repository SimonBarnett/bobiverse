"""FR #9042: worker-remove drops an out_of_fuel nick that exists only in last-good."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import bobreport
import registered_machines as rm

MID = "redqueen"
NICK = "redqueen-7500"


def _fresh_iso() -> str:
    # FR #9145: last-good older than BOB_DIGEST_LAST_GOOD_MAX_S is not exported.
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _home(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rm.sync_from_chanserv(tmp_path, ["#bobiverse", f"#{MID}"])
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def test_remove_drops_out_of_fuel_ghost_from_last_good(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    doc = bobreport.load_digest(home)
    ent = bobreport._machine_entry(doc, MID)
    now = _fresh_iso()
    ent["online"] = True
    ent["worker_list"] = []
    ent["workers"] = {
        "7500": {
            "nick": NICK,
            "state": "out_of_fuel",
            "kind": "grok",
            "working_on": "out-of-fuel",
        }
    }
    ent["workers_last_good"] = [
        {"nick": NICK, "state": "out_of_fuel", "work": "out-of-fuel", "updated": now}
    ]
    ent["workers_last_good_at"] = now
    bobreport.save_digest(home, doc)
    exported = bobreport.export_machine_for_tray(home, MID, ent)
    assert NICK in {w["nick"] for w in (exported.get("workers") or [])}

    out = bobreport.apply_callback(
        home,
        {"op": "worker-remove", "machine": MID, "nick": NICK},
        briefer_nick="Jeeves",
    )
    assert out.ok is True
    assert out.changed is True
    ent2 = bobreport.load_digest(home)["machines"][MID]
    exported2 = bobreport.export_machine_for_tray(home, MID, ent2)
    assert NICK not in {w["nick"] for w in (exported2.get("workers") or [])}
    assert "7500" not in (ent2.get("workers") or {})
    assert not ent2.get("workers_last_good")


def test_remove_unknown_nick_stays_noop(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    assert bobreport.apply_callback(
        home,
        {"op": "worker-upsert", "machine": MID, "nick": "redqueen-1", "state": "idle"},
        briefer_nick="Jeeves",
    ).ok
    out = bobreport.apply_callback(
        home,
        {"op": "worker-remove", "machine": MID, "nick": NICK},
        briefer_nick="Jeeves",
    )
    assert out.ok is True
    assert out.changed is False
    rows = bobreport.load_digest(home)["machines"][MID]["worker_list"]
    assert {r["nick"] for r in rows} == {"redqueen-1"}
