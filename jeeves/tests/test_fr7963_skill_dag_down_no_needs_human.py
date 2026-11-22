"""FR #7963: skill_dag_down GIVEUPs do not stamp needs_human; seat is flagged."""
from __future__ import annotations

import time

import bobreport
import gitclaim
import registered_machines
import shop_listen

REPO = "SimonBarnett/bobiverse"
SEAT_A = "redqueen-644"
SEAT_B = "flamingo-376"
FRESH = "marchhare-18680"


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare", "flamingo", "redqueen"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    for mid, workers in (
        ("redqueen", {"644": {"state": "idle", "nick": SEAT_A}}),
        ("flamingo", {"376": {"state": "idle", "nick": SEAT_B}}),
        ("marchhare", {"18680": {"state": "idle", "nick": FRESH}}),
    ):
        digest["machines"][mid] = bobreport._empty_machine(mid)
        digest["machines"][mid]["workers"] = workers
    bobreport.save_digest(tmp_path, digest)
    return tmp_path


def _accept(doc, nick, ident="#7962"):
    un = [r for r in (doc.get("unaccepted") or []) if r.get("id") == ident]
    if not un:
        return doc
    job = dict(un[0])
    job["nick"] = nick
    doc["unaccepted"] = [r for r in doc["unaccepted"] if r.get("id") != ident]
    doc.setdefault("accepted", []).append(job)
    return doc


def test_is_skill_dag_down_reason_matches_wire_tokens():
    assert gitclaim.is_skill_dag_down_reason("skill_dag_down") is True
    assert gitclaim.is_skill_dag_down_reason("skill_dag_down:exit-1") is True
    assert gitclaim.is_skill_dag_down_reason("SKILL_DAG_DOWN:bad-json:skill=SKILL.md") is True
    # FR #8846
    assert gitclaim.is_skill_dag_down_reason("skill-dag-mcp-down") is True
    assert gitclaim.is_skill_dag_down_reason("skill_dag_mcp_down:cli-failed") is True
    assert gitclaim.is_skill_dag_down_reason("out-of-fuel") is False
    assert gitclaim.is_skill_dag_down_reason("cannot review") is False
    assert gitclaim.is_skill_dag_down_reason("") is False


def test_two_skill_dag_down_giveups_do_not_set_needs_human(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    row = {
        "repo": REPO,
        "task": "FR",
        "id": "#7962",
        "nick": SEAT_A,
        "seq": 1,
        "ts": "t",
        "line": "x",
        "url": f"https://github.com/{REPO}/issues/7962",
        "giveup_count": 0,
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [dict(row)], "done": []},
    )
    for seat, reason in (
        (SEAT_A, "skill_dag_down:exit-1"),
        (SEAT_B, "skill_dag_down:bad-json:skill=SKILL.md"),
    ):
        doc = gitclaim._load_queue_unlocked(home)
        doc = _accept(doc, seat)
        gitclaim._write_queue(gitclaim.queue_path(home), doc)
        st, job = shop_listen.return_job_to_unaccepted(
            home,
            repo=REPO,
            task="FR",
            ident="#7962",
            now=time.time(),
            reason=reason,
        )
        assert st == "ok" and job is not None

    final = [r for r in gitclaim.load_unaccepted(home) if r.get("id") == "#7962"][0]
    assert int(final.get("giveup_count") or 0) == 0
    assert not final.get("needs_human")
    assert gitclaim.row_needs_human(final, FRESH) is False
    seats = {s.strip().lower() for s in str(final.get("giveup_seats") or "").split(",") if s.strip()}
    assert SEAT_A.lower() in seats
    assert SEAT_B.lower() in seats
    assert not str(final.get("cooldown_until") or "").strip()
    st, offered = gitclaim.offer_focus_top(
        home, FRESH, "#marchhare", now=time.time() + 10_000
    )
    assert st == "ok" and offered["id"] == "#7962"
