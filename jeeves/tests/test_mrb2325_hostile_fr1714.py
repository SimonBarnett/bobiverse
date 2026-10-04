"""MRB #2325 hostile gates for FR #1714 workers-map nak-busy heal."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import shop_listen

ROOT = Path(__file__).resolve().parents[2]
IRC = ROOT / "common/scripts/irc_agent.py"
CLAIM = ROOT / "common/scripts/gitclaim.py"


def _no_bom(path: Path) -> None:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path


def _roster(home: Path) -> None:
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["win-mpre8vi4u6u"]}',
        encoding="utf-8",
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None


def test_mrb2325_orphan_clear_before_bored_gate():
    """!bored must heal orphans before busy gate (ordering contract)."""
    _no_bom(IRC)
    text = IRC.read_text(encoding="utf-8")
    assert "clear_orphan_digest_mrb_doing" in text
    assert "bored_gate" in text
    # crude order: orphan clear appears before bored_gate inside _git_bored
    i_fn = text.find("def _git_bored")
    assert i_fn > 0
    chunk = text[i_fn : i_fn + 2500]
    assert chunk.find("clear_orphan_digest_mrb_doing") < chunk.find("bored_gate(")


def test_mrb2325_shop_listen_done_missing_note():
    line = shop_listen.format_shop_listen_info(
        {
            "verb": "DONE",
            "status": "missing",
            "task": "MRB",
            "repo": "SimonBarnett/bobiverse",
            "id": "#1675",
            "activity": None,
        },
        nick="win-mpre8vi4u6u-10960",
    )
    assert "DONE" in line
    assert "missing" in line
    assert "note=missing-acc-still-idle-seat" in line


def test_mrb2325_keep_busy_when_list_doing_open_pr(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    nick = "win-mpre8vi4u6u-10960"
    doc = bobreport.empty_digest()
    doc["machines"]["win-mpre8vi4u6u"] = {
        "id": "win-mpre8vi4u6u",
        "online": True,
        "working_on": "bobiverse MRB #1675",
        "worker_list": [
            {
                "nick": nick,
                "state": "doing",
                "work": "bobiverse MRB #1675",
                "updated": "t",
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
    assert gitclaim.clear_orphan_digest_mrb_doing(
        tmp_path, pr_exists=lambda r, n: True
    ) == 0
    assert "1675" in gitclaim.worker_working_on(tmp_path, nick)


def test_mrb2325_split_brain_heals_and_bored_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    nick = "win-mpre8vi4u6u-10960"
    doc = bobreport.empty_digest()
    doc["machines"]["win-mpre8vi4u6u"] = {
        "id": "win-mpre8vi4u6u",
        "online": True,
        "working_on": "bobiverse MRB #1675",
        "worker_list": [
            {"nick": nick, "state": "idle", "work": "", "updated": "t"}
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
    assert gitclaim.worker_working_on(tmp_path, nick) == ""
    import time

    now = time.time()
    gitclaim.note_worker_activity(tmp_path, nick, now - 10_000)
    assert gitclaim.bored_gate(tmp_path, nick, "#win-mpre8vi4u6u", now) == "ok"
    ent = (bobreport.load_digest(tmp_path).get("machines") or {}).get("win-mpre8vi4u6u") or {}
    assert str(ent.get("working_on") or "") == ""


def test_mrb2325_code_mentions_fr1714_workers_map():
    _no_bom(CLAIM)
    text = CLAIM.read_text(encoding="utf-8")
    assert "1714" in text
    assert "workers" in text
    assert "_orphan_mrb_repo_num" in text or "workers map" in text.lower()
