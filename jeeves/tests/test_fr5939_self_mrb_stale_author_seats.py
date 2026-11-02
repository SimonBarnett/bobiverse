"""FR #5939: self-declared self-mrb and stale author_seats must not block non-authors.

Acceptance:
(a) sibling with no role is offered an MRB whose row has a stale author_seats entry for it
(b) real implementer stays blocked
(c) FIX / fix-PR author stays blocked
(d) self-mrb give-up from a seat with no role does not permanently mark it as an author
Empty-offer detail names implementer / fix / giveup stamp kinds.
"""
from __future__ import annotations

import time

import bobreport
import gitclaim
import registered_machines
import shop_listen

ASEARCH = "SimonBarnett/a-search"
IMPL = "flamingo-60120"
STALE = "flamingo-21424"
FIXER = "flamingo-17668"
OTHER = "marchhare-22372"


def _home(tmp_path, monkeypatch, seats=None):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo", "marchhare"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["workers"] = seats or {
        "60120": {"state": "idle", "nick": IMPL},
        "21424": {"state": "idle", "nick": STALE},
        "17668": {"state": "idle", "nick": FIXER},
    }
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["workers"] = {
        "22372": {"state": "idle", "nick": OTHER},
    }
    bobreport.save_digest(tmp_path, digest)
    return tmp_path


def test_a_stale_author_seats_sibling_is_offerable(tmp_path, monkeypatch):
    """(a) Stale author_seats entry for a no-role sibling must not block MRB offer."""
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": ASEARCH,
                    "task": "MRB",
                    "id": "#5921",
                    "seq": 1,
                    "ts": "t",
                    "line": "x",
                    "url": f"https://github.com/{ASEARCH}/pull/5921",
                    "author_seat": IMPL,
                    "implementer_seat": IMPL,
                    # Pre-#5925 / false self-mrb stamp for a seat with no commits / no FIX.
                    "author_seats": STALE,
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    st, offered = gitclaim.offer_focus_top(
        home, STALE, "#flamingo", now=time.time() + 10_000
    )
    assert st == "ok" and offered and offered["id"] == "#5921"


def test_b_real_implementer_stays_blocked(tmp_path, monkeypatch):
    """(b) Real implementer remains self_mrb-blocked."""
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": ASEARCH,
                    "task": "MRB",
                    "id": "#5921",
                    "seq": 1,
                    "ts": "t",
                    "line": "x",
                    "url": f"https://github.com/{ASEARCH}/pull/5921",
                    "author_seat": IMPL,
                    "implementer_seat": IMPL,
                    "author_seats": STALE,
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    st, _ = gitclaim.offer_focus_top(home, IMPL, "#flamingo", now=time.time() + 10_000)
    assert st != "ok"
    live = gitclaim.live_seat_nicks(home)
    row = gitclaim.load_unaccepted(home)[0]
    enriched = gitclaim.enrich_mrb_author_fields(
        gitclaim._load_queue_unlocked(home), row
    )
    assert gitclaim.review_blocked_for_author(enriched, IMPL, live) is True


def test_c_fix_seat_stays_blocked(tmp_path, monkeypatch):
    """(c) FIX / fix-PR author stays blocked via enrich."""
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": ASEARCH,
                    "task": "MRB",
                    "id": "#5921",
                    "seq": 1,
                    "ts": "t",
                    "line": "x",
                    "url": f"https://github.com/{ASEARCH}/pull/5921",
                    "author_seat": IMPL,
                    "implementer_seat": IMPL,
                }
            ],
            "accepted": [],
            "done": [
                {
                    "repo": ASEARCH,
                    "task": "FIX",
                    "id": "#5921",
                    "nick": FIXER,
                    "done_by": FIXER,
                    "url": f"https://github.com/{ASEARCH}/pull/5921",
                }
            ],
        },
    )
    st, _ = gitclaim.offer_focus_top(home, FIXER, "#flamingo", now=time.time() + 10_000)
    assert st != "ok"
    live = gitclaim.live_seat_nicks(home)
    doc = gitclaim._load_queue_unlocked(home)
    enriched = gitclaim.enrich_mrb_author_fields(doc, doc["unaccepted"][0])
    assert FIXER in gitclaim.row_author_seats(enriched)
    assert gitclaim.review_blocked_for_author(enriched, FIXER, live) is True


def test_d_self_mrb_giveup_no_role_does_not_stamp_author(tmp_path, monkeypatch):
    """(d) Bare self-mrb give-up from a no-role seat -> giveup_seats only."""
    home = _home(tmp_path, monkeypatch)
    row = {
        "repo": ASEARCH,
        "task": "MRB",
        "id": "#5921",
        "nick": STALE,
        "seq": 1,
        "ts": "t",
        "line": "x",
        "url": f"https://github.com/{ASEARCH}/pull/5921",
        "author_seat": IMPL,
        "implementer_seat": IMPL,
        "giveup_count": 0,
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [dict(row)], "done": []},
    )
    st, job = shop_listen.return_job_to_unaccepted(
        home,
        repo=ASEARCH,
        task="MRB",
        ident="#5921",
        now=time.time(),
        reason="self-MRB",
    )
    assert st == "ok" and job is not None
    assert int(job.get("giveup_count") or 0) == 0
    assert not job.get("needs_human")
    assert STALE.lower() in str(job.get("giveup_seats") or "").lower()
    authors = [a.lower() for a in gitclaim.row_author_seats(job)]
    assert STALE.lower() not in authors
    assert IMPL.lower() in authors
    # After enrich, stale must still be absent and STALE offerable once giveup cleared
    # for a *different* seat; STALE itself stays blocked via giveup_seats.
    st_stale, _ = gitclaim.offer_focus_top(
        home, STALE, "#flamingo", now=time.time() + 10_000
    )
    assert st_stale != "ok"
    st_other, offered = gitclaim.offer_focus_top(
        home, OTHER, "#marchhare", now=time.time() + 20_000
    )
    assert st_other == "ok" and offered["id"] == "#5921"


def test_empty_offer_names_stamp_kinds(tmp_path, monkeypatch):
    """Empty-offer log names implementer / fix / giveup stamp kinds (FR #5939)."""
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": ASEARCH,
                    "task": "MRB",
                    "id": "#1",
                    "seq": 1,
                    "ts": "t",
                    "line": "x",
                    "url": f"https://github.com/{ASEARCH}/pull/1",
                    "author_seat": IMPL,
                    "implementer_seat": IMPL,
                },
                {
                    "repo": ASEARCH,
                    "task": "MRB",
                    "id": "#2",
                    "seq": 2,
                    "ts": "t",
                    "line": "x",
                    "url": f"https://github.com/{ASEARCH}/pull/2",
                    "author_seat": "marchhare-1",
                    "implementer_seat": "marchhare-1",
                    "mrb_fix_author_seat": IMPL,
                    "author_seats": IMPL,
                },
                {
                    "repo": ASEARCH,
                    "task": "MRB",
                    "id": "#3",
                    "seq": 3,
                    "ts": "t",
                    "line": "x",
                    "url": f"https://github.com/{ASEARCH}/pull/3",
                    "author_seat": "marchhare-2",
                    "giveup_seats": IMPL,
                },
            ],
            "accepted": [],
            "done": [],
        },
    )
    stats = gitclaim.summarize_empty_offer(home, IMPL)
    detail = gitclaim.format_empty_offer_detail(IMPL, stats)
    assert "implementer=" in detail or "stamp=implementer" in detail or "implementer" in detail
    assert "fix=" in detail or "stamp=fix" in detail
    assert "giveup=" in detail or "stamp=giveup" in detail
    assert int(stats.get("stamp_implementer") or stats.get("implementer") or 0) >= 1
    assert int(stats.get("stamp_fix") or stats.get("fix") or 0) >= 1
    assert int(stats.get("stamp_giveup") or stats.get("giveup") or 0) >= 1


def test_classify_mrb_author_stamp_kinds(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)  # register flamingo so parse_seat_nick works
    impl_row = {
        "task": "MRB",
        "implementer_seat": IMPL,
        "author_seat": IMPL,
    }
    assert gitclaim.classify_mrb_author_stamp(impl_row, IMPL) == "implementer"
    fix_row = {
        "task": "MRB",
        "author_seat": "marchhare-1",
        "mrb_fix_author_seat": FIXER,
        "author_seats": FIXER,
    }
    assert gitclaim.classify_mrb_author_stamp(fix_row, FIXER) == "fix"
    assert gitclaim.classify_mrb_author_stamp(impl_row, STALE) == ""
