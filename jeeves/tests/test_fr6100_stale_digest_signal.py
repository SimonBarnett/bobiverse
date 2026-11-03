"""FR #6100: stale public digest is flagged; hung own lock recovers."""
from __future__ import annotations

import json
import os
import time
from argparse import Namespace
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys

_MON = Path(__file__).resolve().parents[1] / "tools" / "monitor"
if str(_MON) not in sys.path:
    sys.path.insert(0, str(_MON))

import bobcallback
import bobreport
import stall_detectors as sd

import registered_machines as rm


def _iso(hours_ago: float) -> str:
    dt = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _home(tmp_path: Path, ts: str) -> Path:
    rm.sync_from_chanserv(tmp_path, ["#bobiverse", "#flamingo"])
    doc = bobreport.empty_digest()
    doc["ts"] = ts
    mid = "flamingo"
    doc["machines"][mid] = bobreport._empty_machine(mid)
    doc["machines"][mid]["lastSeen"] = ts
    doc["machines"][mid]["online"] = True
    bobreport.save_digest(tmp_path, doc)
    return tmp_path


def test_fr6100_iso_ts_marks_digest_stale():
    now = datetime.now(timezone.utc)
    doc = {"ts": _iso(20), "machines": {"flamingo": {"lastSeen": _iso(20)}}}
    assert bobreport.digest_is_stale(doc, now=now) is True
    assert (bobreport.digest_age_s(doc, now=now) or 0) > 19 * 3600
    fresh = {"ts": _iso(0.01), "machines": {}}
    assert bobreport.digest_is_stale(fresh, now=now) is False


def test_fr6100_build_digest_object_sets_stale_flag(tmp_path):
    _home(tmp_path, _iso(20))
    obj = bobreport.build_digest_object(tmp_path, "Jeeves")
    assert obj.get("stale") is True
    assert obj.get("airc_consoles_stale") is True
    assert int(obj.get("stale_age_s") or 0) > 19 * 3600
    code, raw = bobcallback.handle_digest_get(tmp_path, "Jeeves")
    assert code == 200
    got = json.loads(raw.decode("utf-8"))
    assert got.get("stale") is True


def test_fr6100_monitor_uses_iso_ts_not_mtime(tmp_path, monkeypatch):
    home = _home(tmp_path, _iso(20))
    # Touch the file so mtime looks fresh — the old monitor would false-ok.
    path = home / "digest.json"
    now = time.time()
    os.utime(path, (now, now))
    import stale_digest as sdg

    args = Namespace(chair_home=str(home), digest_home=str(home), dry_run=False)
    payload, code = sdg.check(args)
    assert code == 1
    assert payload.get("ok") is False
    assert any("stale" in f for f in payload.get("findings") or [])


def test_fr6100_stall_detector_files_digest_frozen():
    snap = {"now": time.time(), "digest_ts": _iso(20), "digest_last_seen": [_iso(20)]}
    found = sd.detect_stale_digest(snap)
    assert len(found) == 1
    assert found[0]["id"] == sd.STALE_DIGEST_ID
    all_f = sd.detect_all(snap)
    assert any(x.get("fingerprint") == "stall:stale-digest:report" for x in all_f)
    healthy = {"now": time.time(), "digest_ts": _iso(0.01)}
    assert sd.detect_stale_digest(healthy) == []


def test_fr6100_hung_own_lock_breaks_when_digest_content_stale(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_LOCK_STALE_S", "5")
    monkeypatch.setenv("BOB_DIGEST_STALE_S", "60")
    home = _home(tmp_path, _iso(2))
    lock = bobreport.digest_lock_path(home)
    lock.parent.mkdir(parents=True, exist_ok=True)
    me = os.getpid()
    lock.write_text(f"{me}\n{time.time():.3f}\n", encoding="utf-8")
    old = time.time() - 7200
    os.utime(lock, (old, old))
    info = bobreport.break_stale_digest_lock(home)
    assert info is not None
    assert info.get("reason") == "hung-own-content-stale"
    assert not lock.exists()
