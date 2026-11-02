"""FR #5947: digest airc_consoles includes customer-channel *_console nicks."""
from __future__ import annotations

import bobreport
import chan_workers
import registered_machines


def _shop_home(tmp_path, mid="flamingo"):
    registered_machines.save_registered(tmp_path, {mid})
    digest = bobreport.empty_digest()
    digest["machines"][mid] = bobreport._empty_machine(mid)
    digest["machines"][mid]["online"] = True
    bobreport.save_digest(tmp_path, digest)
    return mid


def test_fr5947_customer_channel_console_appears_in_airc_consoles(tmp_path):
    mid = _shop_home(tmp_path)
    wk = chan_workers.WorkerTracker(tmp_path, log=lambda _m: None)
    wk.reconcile(
        "#hrs-priority-dev",
        {"hrs-priority-dev_console", "someone-else", "Jeeves"},
    )
    obj = bobreport.build_digest_object(tmp_path, "Jeeves")
    assert "hrs-priority-dev_console" in obj["airc_consoles"]
    assert obj["machines"][mid]["console_nicks"] == []
    details = obj.get("airc_console_details") or []
    hit = [r for r in details if str(r.get("nick") or "").lower() == "hrs-priority-dev_console"]
    assert hit, details
    assert hit[0].get("channel", "").lower() == "#hrs-priority-dev"
    assert "hrs-priority-dev" in str(hit[0].get("machine") or "").lower()
    blob = str(obj)
    assert "password" not in blob.lower()
    assert "nickserv" not in blob.lower()


def test_fr5947_customer_console_clears_on_part(tmp_path):
    _shop_home(tmp_path)
    wk = chan_workers.WorkerTracker(tmp_path, log=lambda _m: None)
    wk.reconcile("#hrs-priority-dev", {"hrs-priority-dev_console"})
    assert "hrs-priority-dev_console" in bobreport.build_digest_object(tmp_path, "Jeeves")["airc_consoles"]
    wk.on_leave("hrs-priority-dev_console", "#hrs-priority-dev")
    assert "hrs-priority-dev_console" not in bobreport.build_digest_object(tmp_path, "Jeeves")["airc_consoles"]


def test_fr5947_customer_console_clears_on_quit(tmp_path):
    _shop_home(tmp_path)
    wk = chan_workers.WorkerTracker(tmp_path, log=lambda _m: None)
    wk.reconcile("#cust-a", {"hrs-priority-dev_console"})
    wk.reconcile("#cust-b", {"hrs-priority-dev_console"})
    assert "hrs-priority-dev_console" in bobreport.build_digest_object(tmp_path, "Jeeves")["airc_consoles"]
    wk.on_quit("hrs-priority-dev_console")
    assert "hrs-priority-dev_console" not in bobreport.build_digest_object(tmp_path, "Jeeves")["airc_consoles"]


def test_fr5947_shop_consoles_unchanged(tmp_path):
    mid = _shop_home(tmp_path)
    wk = chan_workers.WorkerTracker(tmp_path, log=lambda _m: None)
    wk.reconcile(f"#{mid}", {"flamingo_console", "flamingo-9"})
    wk.reconcile("#hrs-priority-dev", {"hrs-priority-dev_console"})
    obj = bobreport.build_digest_object(tmp_path, "Jeeves")
    assert obj["machines"][mid]["console_nicks"] == ["flamingo_console"]
    assert set(obj["airc_consoles"]) == {"flamingo_console", "hrs-priority-dev_console"}
