"""FR #5204: GET /bob/v1/report lists live *_console nicks without NickServ."""
from __future__ import annotations

import bobreport
import chan_workers
import registered_machines


def _home(tmp_path, mid="flamingo"):
    registered_machines.save_registered(tmp_path, {mid})
    digest = bobreport.empty_digest()
    digest["machines"][mid] = bobreport._empty_machine(mid)
    digest["machines"][mid]["online"] = True
    bobreport.save_digest(tmp_path, digest)
    return mid


def test_console_nicks_from_present_filters_suffix():
    got = bobreport.console_nicks_from_present(
        {"flamingo_console", "flamingo-123", "Bob-flamingo", "ionos_console"}
    )
    assert got == ["flamingo_console", "ionos_console"]


def test_digest_export_lists_airc_consoles(tmp_path):
    mid = _home(tmp_path)
    bobreport.set_machine_console_nicks(tmp_path, mid, ["flamingo_console", "x"])
    obj = bobreport.build_digest_object(tmp_path, "Jeeves")
    assert obj["airc_consoles"] == ["flamingo_console"]
    assert obj["machines"][mid]["console_nicks"] == ["flamingo_console"]
    blob = str(obj)
    assert "password" not in blob.lower()
    assert "nickserv" not in blob.lower()


def test_names_reconcile_records_shop_consoles(tmp_path):
    mid = _home(tmp_path)
    wk = chan_workers.WorkerTracker(tmp_path, log=lambda _m: None)
    wk.reconcile(
        f"#{mid}",
        {"flamingo-9", "flamingo_console", "Jeeves"},
    )
    obj = bobreport.build_digest_object(tmp_path, "Jeeves")
    assert obj["airc_consoles"] == ["flamingo_console"]
    wk.reconcile(f"#{mid}", {"flamingo-9"})
    obj2 = bobreport.build_digest_object(tmp_path, "Jeeves")
    assert obj2["airc_consoles"] == []


def test_console_part_drops_nick(tmp_path):
    mid = _home(tmp_path)
    bobreport.set_machine_console_nicks(tmp_path, mid, ["flamingo_console"])
    wk = chan_workers.WorkerTracker(tmp_path, log=lambda _m: None)
    wk.on_leave("flamingo_console", f"#{mid}")
    obj = bobreport.build_digest_object(tmp_path, "Jeeves")
    assert obj["airc_consoles"] == []
