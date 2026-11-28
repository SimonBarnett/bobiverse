"""FR #10327: jeeves.exe title pins walrus; offer-gap + body-line do not."""
from __future__ import annotations

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines


TITLE_10119 = (
    "jeeves.exe: chair+BobCallback one process, self-test/heal, rock-solid webhooks"
)
BODY_10119 = (
    "require_machine: ionos\n\n"
    "WP4 ionos cutover. Refs living architecture #1993.\n"
)


def test_fr10327_jeeves_exe_title_pins_walrus_without_label():
    mid = gitclaim.infer_require_machine(
        title=TITLE_10119,
        body=BODY_10119,
        labels=["feature-request"],
        repo="SimonBarnett/bobiverse",
        ident="#10119",
    )
    assert mid == "walrus"


def test_fr10327_offer_gap_receipt_stays_unpinned():
    mid = gitclaim.infer_require_machine(
        title="Chair offered ionos-pinned FR #10119 to redqueen shop",
        body=(
            "Evidence: issue body require_machine: ionos; worker GIVEUP require_machine=ionos.\n"
            "Fix: chair should stamp require_machine=ionos and not offer to non-ionos shops.\n"
        ),
        labels=["via-intake"],
        repo="SimonBarnett/bobiverse",
        ident="#10327",
    )
    assert mid == ""


def test_fr10327_offer_focus_skips_redqueen_for_10119_shape(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"walrus", "redqueen", "marchhare"})
    doc = bobreport.empty_digest()
    for mid, pid in (("walrus", 1), ("redqueen", 7376), ("marchhare", 21904)):
        doc["machines"][mid] = bobreport._empty_machine(mid)
        doc["machines"][mid]["worker_list"] = [
            {
                "nick": f"{mid}-{pid}",
                "state": "idle",
                "work": "",
                "updated": "2026-11-28T13:00:00Z",
            }
        ]
    bobreport.save_digest(home, doc)
    row = {
        "task": "FR",
        "repo": "SimonBarnett/bobiverse",
        "id": "#10119",
        "seq": 1,
        "ts": "t",
        "line": "FR SimonBarnett/bobiverse#10119",
        "title": TITLE_10119,
        "body": gitclaim._body_for_queue(BODY_10119),
        "labels": ["feature-request"],
        "state": "open",
    }
    gitclaim._stamp_require_machine(row)
    assert gitclaim.row_require_machine(row) == "walrus"
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    fi.handle_focus_cmd(home, "hi bobiverse")

    st_rq, job_rq = gitclaim.offer_focus_top(home, "redqueen-7376", "#redqueen")
    assert st_rq == "empty"
    assert job_rq is None

    st_mh, job_mh = gitclaim.offer_focus_top(home, "marchhare-21904", "#marchhare")
    assert st_mh == "empty"
    assert job_mh is None

    st_w, job_w = gitclaim.offer_focus_top(home, "walrus-1", "#walrus")
    assert st_w == "ok"
    assert job_w is not None
    assert str(job_w.get("id") or "").lstrip("#") == "10119"