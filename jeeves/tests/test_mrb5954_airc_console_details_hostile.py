"""docs/mrb-5954: hostile pins for customer airc_console_details / presence."""
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


def test_mrb5954_part_one_channel_keeps_other(tmp_path):
    _shop_home(tmp_path)
    wk = chan_workers.WorkerTracker(tmp_path, log=lambda _m: None)
    wk.reconcile("#cust-a", {"hrs-priority-dev_console"})
    wk.reconcile("#cust-b", {"hrs-priority-dev_console"})
    obj = bobreport.build_digest_object(tmp_path, "Jeeves")
    assert "hrs-priority-dev_console" in obj["airc_consoles"]
    wk.on_leave("hrs-priority-dev_console", "#cust-a")
    obj2 = bobreport.build_digest_object(tmp_path, "Jeeves")
    assert "hrs-priority-dev_console" in obj2["airc_consoles"]
    kept = [
        r
        for r in (obj2.get("airc_console_details") or [])
        if str(r.get("nick") or "").lower() == "hrs-priority-dev_console"
    ]
    assert len(kept) == 1 and kept[0].get("channel", "").lower() == "#cust-b"


def test_mrb5954_details_keys_credential_free(tmp_path):
    _shop_home(tmp_path)
    wk = chan_workers.WorkerTracker(tmp_path, log=lambda _m: None)
    wk.reconcile("#hrs-priority-dev", {"hrs-priority-dev_console"})
    obj = bobreport.build_digest_object(tmp_path, "Jeeves")
    details = obj.get("airc_console_details") or []
    assert details
    for row in details:
        assert set(row.keys()) <= {"nick", "channel", "machine"}
    blob = str(obj).lower()
    assert "password" not in blob
    assert "nickserv" not in blob
    assert "token" not in blob


def test_mrb5954_docs_cite_5947_and_details():
    from pathlib import Path

    ear = Path(__file__).resolve().parents[2] / "bob" / "docs" / "bob-ear.md"
    text = ear.read_text(encoding="utf-8")
    assert "FR #5947" in text
    assert "airc_console_details" in text
    assert not ear.read_bytes().startswith(b"\xef\xbb\xbf")
