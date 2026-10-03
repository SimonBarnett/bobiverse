"""FR #1323: after DONE MRB (PASS/FAIL), do not re-offer same row_key — even if done trimmed or offered_to lingers."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import registered_machines
import shop_listen


REPO = "SimonBarnett/Club-Madeira"


def _digest(home: Path) -> None:
    registered_machines.save_registered(home, {"marchhare", "flamingo", "win-mpre8vi4u6u"})
    digest = bobreport.empty_digest()
    for mid, wid in (("marchhare", "41928"), ("flamingo", "9"), ("win-mpre8vi4u6u", "1")):
        digest["machines"][mid] = bobreport._empty_machine(mid)
        digest["machines"][mid]["workers"] = {wid: {"state": "idle"}}
    bobreport.save_digest(home, digest)


def _mrb(num=10, **extra):
    row = {
        "repo": REPO,
        "task": "MRB",
        "id": f"#{num}",
        "seq": 1,
        "ts": "t",
        "line": f"MRB {REPO}#{num}",
        "url": f"https://github.com/{REPO}/pull/{num}",
    }
    row.update(extra)
    return row


def test_done_mrb_stamps_ledger_mrb_done(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [_mrb(10, nick="marchhare-41928")], "done": []},
    )
    st, job = shop_listen.complete_job_by_ref(
        tmp_path,
        nick="marchhare-41928",
        repo=REPO,
        task="MRB",
        ident="#10",
        result="PASS",
        url=f"https://github.com/{REPO}/pull/10",
    )
    assert st == "ok"
    assert job.get("result") == "PASS"
    led = gitclaim.ledger_load(tmp_path)
    key = gitclaim._lkey(REPO, "#10")
    assert key in (led.get("mrb_done") or {})


def test_offer_skips_mrb_after_ledger_hold_even_if_done_trimmed(tmp_path, monkeypatch):
    """done[] may rotate out (ACCEPTED_CAP); ledger mrb_done must still block re-offer."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest(tmp_path)
    key = gitclaim._lkey(REPO, "#10")

    def _stamp(doc):
        doc.setdefault("mrb_done", {})[key] = gitclaim._utc_now()

    gitclaim._ledger_update(tmp_path, _stamp)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            # no done[] entry — simulates trim
            "unaccepted": [_mrb(10)],
            "accepted": [],
            "done": [],
        },
    )
    st, job = gitclaim.offer_focus_top(tmp_path, "marchhare-41928", "#marchhare")
    assert st == "empty"
    assert gitclaim.load_unaccepted(tmp_path) == []


def test_resync_drops_merged_mrb_even_with_offered_to(tmp_path, monkeypatch):
    """FR #1323: offered_to must not preserve MERGED MRB rows across resync."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    doc = {
        "v": 1,
        "unaccepted": [
            _mrb(10, offered_to="marchhare-41928", offered_ts="t", offered_channel="#marchhare")
        ],
        "accepted": [],
        "done": [],
    }
    # Simulate resync keep filter: not in want (merged), but had offered_to
    want = set()  # no open pulls
    fetched_set = {REPO}
    keep = []
    for row in doc["unaccepted"]:
        if (
            row.get("repo") in fetched_set
            and row.get("task") in ("FR", "MRB")
            and (row.get("repo"), row.get("task"), row.get("id")) not in want
            and not gitclaim.mrb_row_should_survive_resync(row, want=want, fetched=fetched_set)
        ):
            continue
        keep.append(row)
    assert keep == []


def test_same_nick_not_reoffered_after_done_pass(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [_mrb(10, nick="marchhare-41928")], "done": []},
    )
    shop_listen.complete_job_by_ref(
        tmp_path,
        nick="marchhare-41928",
        repo=REPO,
        task="MRB",
        ident="#10",
        result="PASS",
        url=f"https://github.com/{REPO}/pull/10",
    )
    done_rows = list(gitclaim._load_queue_unlocked(tmp_path).get("done") or [])
    assert any(str(r.get("id")) == "#10" for r in done_rows)
    # Phantom unaccepted reappears (resync race) while done/ledger still hold
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [_mrb(10)],
            "accepted": [],
            "done": done_rows,
        },
    )
    st, _ = gitclaim.offer_focus_top(tmp_path, "marchhare-41928", "#marchhare")
    assert st == "empty"
    st2, _ = gitclaim.offer_focus_top(tmp_path, "flamingo-9", "#flamingo")
    assert st2 == "empty"
