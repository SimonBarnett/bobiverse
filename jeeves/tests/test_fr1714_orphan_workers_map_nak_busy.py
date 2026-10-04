"""FR #1714: idle worker_list + stale workers map must not nak-busy forever."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim


def _roster(home: Path) -> None:
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["win-mpre8vi4u6u"]}',
        encoding="utf-8",
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None


def _digest_split_brain(home: Path, *, nick: str = "win-mpre8vi4u6u-10960", pr: str = "1675") -> None:
    """worker_list idle, workers map still running+working_on (live evidence shape)."""
    pid = nick.rsplit("-", 1)[-1]
    doc = bobreport.empty_digest()
    doc["machines"]["win-mpre8vi4u6u"] = {
        "id": "win-mpre8vi4u6u",
        "online": True,
        "working_on": f"bobiverse MRB #{pr}",
        "worker_list": [
            {
                "nick": nick,
                "state": "idle",
                "work": "",
                "updated": "2026-10-04T13:47:44Z",
            }
        ],
        "workers": {
            pid: {
                "pid": pid,
                "nick": nick,
                "state": "running",
                "working_on": f"bobiverse MRB #{pr}",
            }
        },
    }
    bobreport.save_digest(home, doc)


def test_fr1714_worker_working_on_heals_map_when_list_idle(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    nick = "win-mpre8vi4u6u-10960"
    _digest_split_brain(tmp_path, nick=nick, pr="1675")
    assert gitclaim.worker_working_on(tmp_path, nick) == ""
    d2 = bobreport.load_digest(tmp_path)
    ent = (d2.get("machines") or {}).get("win-mpre8vi4u6u") or {}
    w = ((ent.get("workers") or {}).get("10960") or {})
    assert str(w.get("state") or "") == "idle"
    assert str(w.get("working_on") or "") == ""
    assert str(ent.get("working_on") or "") == ""


def test_fr1714_bored_gate_ok_after_split_brain_heal(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    nick = "win-mpre8vi4u6u-10960"
    _digest_split_brain(tmp_path, nick=nick)
    import time

    now = time.time()
    # Ensure activity is old enough to pass IDLE_S wait gate.
    gitclaim.note_worker_activity(tmp_path, nick, now - 10_000)
    assert gitclaim.bored_gate(tmp_path, nick, "#win-mpre8vi4u6u", now) == "ok"


def test_fr1714_clear_orphan_scans_workers_map_when_list_idle(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    nick = "win-mpre8vi4u6u-10960"
    # Both list and map still doing — classic orphan after ACC gone.
    doc = bobreport.empty_digest()
    doc["machines"]["win-mpre8vi4u6u"] = {
        "id": "win-mpre8vi4u6u",
        "online": True,
        "worker_list": [
            {
                "nick": nick,
                "state": "doing",
                "work": "bobiverse MRB #1675",
                "updated": "2026-10-04T13:40:00Z",
            }
        ],
        "workers": {
            "10960": {
                "pid": "10960",
                "nick": nick,
                "state": "running",
                "working_on": "bobiverse MRB #1675",
            }
        },
    }
    bobreport.save_digest(tmp_path, doc)

    def pr_exists(repo, num):
        return False

    n = gitclaim.clear_orphan_digest_mrb_doing(tmp_path, pr_exists=pr_exists)
    assert n >= 1
    assert gitclaim.worker_working_on(tmp_path, nick) == ""


def test_fr1714_clear_orphan_workers_map_only(tmp_path, monkeypatch):
    """List already idle; map still busy with dead MRB — clear_orphan must still heal."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    nick = "win-mpre8vi4u6u-10960"
    _digest_split_brain(tmp_path, nick=nick, pr="1675")

    def pr_exists(repo, num):
        return False

    n = gitclaim.clear_orphan_digest_mrb_doing(tmp_path, pr_exists=pr_exists)
    assert n >= 1
    d2 = bobreport.load_digest(tmp_path)
    w = (((d2.get("machines") or {}).get("win-mpre8vi4u6u") or {}).get("workers") or {}).get("10960") or {}
    assert str(w.get("working_on") or "") == ""


def test_fr1714_keep_seats_busy_when_list_still_doing_open_pr(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    nick = "win-mpre8vi4u6u-10960"
    doc = bobreport.empty_digest()
    doc["machines"]["win-mpre8vi4u6u"] = {
        "id": "win-mpre8vi4u6u",
        "online": True,
        "worker_list": [
            {
                "nick": nick,
                "state": "doing",
                "work": "bobiverse MRB #1675",
                "updated": "2026-10-04T13:40:00Z",
            }
        ],
        "workers": {
            "10960": {
                "pid": "10960",
                "state": "running",
                "working_on": "bobiverse MRB #1675",
            }
        },
    }
    bobreport.save_digest(tmp_path, doc)

    def pr_exists(repo, num):
        return True  # still open

    assert gitclaim.clear_orphan_digest_mrb_doing(tmp_path, pr_exists=pr_exists) == 0
    assert "1675" in gitclaim.worker_working_on(tmp_path, nick)
