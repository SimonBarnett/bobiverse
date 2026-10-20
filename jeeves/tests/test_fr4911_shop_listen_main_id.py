"""FR #4911: shop-listen must parse #main / #main-red; retire main-red when main is green."""
from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

shop_listen = importlib.import_module("shop_listen")
gitclaim = importlib.import_module("gitclaim")
mrb_merge_on_green = importlib.import_module("mrb_merge_on_green")

REPO = "SimonBarnett/a-search"
NICK = "flamingo-73012"
URL = f"https://github.com/{REPO}/commit/{'a' * 40}"
MAIN_SHA = "a" * 40
NEW_SHA = "c" * 40


def _seed_accepted_main(home: Path, *, nick: str = NICK) -> None:
    home.mkdir(parents=True, exist_ok=True)
    sig = mrb_merge_on_green.main_red_fix_signature(REPO, MAIN_SHA, "test-and-synth")
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [
                {
                    "repo": REPO,
                    "task": "FIX",
                    "id": "#main",
                    "nick": nick,
                    "url": URL,
                    "pass_sha": MAIN_SHA,
                    "fail_signature": sig,
                    "main_red_fix": "1",
                    "accepted_ts": "2026-10-20T17:36:30Z",
                }
            ],
            "done": [],
        },
    )


def test_parse_done_fix_main():
    p = shop_listen.parse_shop_job_line(f"DONE FIX {REPO}#main {URL}")
    assert p is not None
    assert p.verb == "DONE" and p.task == "FIX"
    assert p.id == "#main"
    assert p.repo == REPO
    assert p.url == URL or URL in (p.result or "")


def test_parse_ack_fix_main_red_case():
    p = shop_listen.parse_shop_job_line(f"ACK FIX {REPO}#MAIN-RED main red suite")
    assert p is not None
    assert p.id == "#main-red"
    assert p.verb == "ACK"


def test_parse_giveup_and_nack_main():
    g = shop_listen.parse_shop_job_line(f"GIVEUP FIX {REPO}#main out of fuel")
    n = shop_listen.parse_shop_job_line(f"NACK FIX {REPO}#main wrong box")
    assert g is not None and g.id == "#main" and g.verb == "GIVEUP"
    assert n is not None and n.id == "#main" and n.verb == "NACK"


def test_done_fix_main_moves_to_done_and_clears_hold(tmp_path: Path):
    home = tmp_path / "home"
    _seed_accepted_main(home)
    gitclaim.note_seat_hold(
        home,
        NICK,
        {"repo": REPO, "task": "FIX", "id": "#main"},
        via="ack",
    )
    parsed = shop_listen.parse_shop_job_line(f"DONE FIX {REPO}#main {URL}")
    assert parsed is not None
    st, job = shop_listen.complete_job_by_ref(
        home,
        nick=NICK,
        repo=parsed.repo,
        task=parsed.task,
        ident=parsed.id,
        result=parsed.result,
        url=parsed.url,
    )
    assert st == "ok"
    assert job is not None
    after = gitclaim._load_queue_unlocked(home)
    assert after.get("accepted") == []
    assert any(str(r.get("id")) == "#main" for r in (after.get("done") or []))
    gitclaim.clear_seat_hold(
        home, NICK, repo=REPO, task="FIX", ident="#main", clear_pins=True
    )
    holds = gitclaim._load_seat_holds_unlocked(home)
    seats = holds.get("seats") if isinstance(holds, dict) else None
    if isinstance(seats, dict):
        assert NICK.lower() not in {str(k).lower() for k in seats} or not seats.get(
            NICK
        )


def test_giveup_fix_main_returns_unaccepted(tmp_path: Path):
    home = tmp_path / "home"
    _seed_accepted_main(home)
    parsed = shop_listen.parse_shop_job_line(f"GIVEUP FIX {REPO}#main blocked")
    assert parsed is not None
    st, job = shop_listen.return_job_to_unaccepted(
        home,
        repo=parsed.repo,
        task=parsed.task,
        ident=parsed.id,
        reason=parsed.rest or "",
    )
    assert st == "ok"
    after = gitclaim._load_queue_unlocked(home)
    assert after.get("accepted") == []
    assert any(str(r.get("id")) == "#main" for r in (after.get("unaccepted") or []))


def test_stale_busy_main_red_when_main_green_drops_not_requeue(tmp_path, monkeypatch):
    import bobreport

    home = tmp_path / "home"
    _seed_accepted_main(home)
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["flamingo"]}', encoding="utf-8"
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = {
        "id": "flamingo",
        "online": True,
        "working_on": "a-search FIX #main",
        "worker_list": [
            {
                "nick": NICK,
                "state": "doing",
                "work": "a-search FIX #main",
                "updated": "2026-10-20T17:37:00Z",
            }
        ],
        "workers": {
            "73012": {
                "pid": "73012",
                "nick": NICK,
                "state": "doing",
                "working_on": "a-search FIX #main",
            }
        },
    }
    bobreport.save_digest(home, digest)

    # Age the ACC past BUSY_STALE_S.
    now = time.time()
    old = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - gitclaim.BUSY_STALE_S - 60)
    )
    doc = gitclaim._load_queue_unlocked(home)
    doc["accepted"][0]["accepted_ts"] = old
    gitclaim._write_queue(gitclaim.queue_path(home), doc)

    monkeypatch.setattr(
        mrb_merge_on_green, "main_branch_checks_red", lambda *_a, **_k: False
    )
    monkeypatch.setattr(
        mrb_merge_on_green,
        "main_branch_head_sha",
        lambda *_a, **_k: MAIN_SHA,
    )

    assert gitclaim.release_stale_busy(home, NICK, now) is True
    after = gitclaim._load_queue_unlocked(home)
    assert after.get("accepted") == []
    unacc = after.get("unaccepted") or []
    assert not any(str(r.get("id")) == "#main" for r in unacc)
    done = after.get("done") or []
    hit = [r for r in done if str(r.get("id")) == "#main"]
    assert hit
    assert "requeue:STALE_BUSY" not in str(hit[0].get("reconcile") or "")
    assert "MAIN_GREEN" in str(hit[0].get("result") or hit[0].get("reconcile") or "")


def test_purge_main_red_when_main_green(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    sig = mrb_merge_on_green.main_red_fix_signature(REPO, MAIN_SHA, "test-and-synth")
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": REPO,
                    "task": "FIX",
                    "id": "#main",
                    "pass_sha": MAIN_SHA,
                    "fail_signature": sig,
                    "main_red_fix": "1",
                    "url": URL,
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    doc = gitclaim._load_queue_unlocked(home)
    n = gitclaim._purge_dead_fix_unaccepted(
        doc,
        main_red_by_repo={REPO: False},
        main_sha_by_repo={REPO: MAIN_SHA},
    )
    assert n == 1
    assert doc.get("unaccepted") == []


def test_purge_main_red_when_signature_sha_not_head(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    sig = mrb_merge_on_green.main_red_fix_signature(REPO, MAIN_SHA, "test-and-synth")
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": REPO,
                    "task": "FIX",
                    "id": "#main",
                    "pass_sha": MAIN_SHA,
                    "fail_signature": sig,
                    "main_red_fix": "1",
                    "url": URL,
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    doc = gitclaim._load_queue_unlocked(home)
    # Main still red, but head moved past the signature SHA.
    n = gitclaim._purge_dead_fix_unaccepted(
        doc,
        main_red_by_repo={REPO: True},
        main_sha_by_repo={REPO: NEW_SHA},
    )
    assert n == 1
    assert doc.get("unaccepted") == []


def test_numeric_id_still_parses():
    p = shop_listen.parse_shop_job_line(
        "DONE FR SimonBarnett/bobiverse#4911 https://github.com/SimonBarnett/bobiverse/pull/1"
    )
    assert p is not None and p.id == "#4911"
