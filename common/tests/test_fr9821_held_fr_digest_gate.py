# -*- coding: utf-8 -*-
"""FR #9821: never offer children of held fr-digest; Digests created with hold.

Fail-when: child Depends-on OPEN fr-digest+hold is offered / counted offerable.
Held vs unheld: unhold releases the child. Intake stamps hold on Digest parents.
Enqueue: held digests enter the queue as gate records (token-free gate).
"""
from __future__ import annotations

import sys
from pathlib import Path

import bobreport
import focus_ignore as fi
import gitclaim
import intake
import registered_machines
import stuck_job_sweep
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "common" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import fr_digest_gate  # noqa: E402

REPO = "SimonBarnett/bobiverse"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"marchhare", "flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [
        {
            "nick": "marchhare-35600",
            "state": "idle",
            "kind": "grok",
            "start_model": "grok-4",
            "configured_model": "grok-4",
            "updated": "2026-11-24T12:00:00Z",
        }
    ]
    bobreport.save_digest(tmp_path, digest)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return tmp_path


def _row(num: int, seq: int, **kw) -> dict:
    r = {
        "repo": REPO,
        "task": "FR",
        "id": f"#{num}",
        "seq": seq,
        "ts": f"2026-11-24T10:00:{num:02d}Z",
        "line": f"FR {REPO}#{num}",
        "url": f"https://github.com/{REPO}/issues/{num}",
        "title": f"FR {num}",
        "state": "open",
        "body": "Depends-on: (none)\n",
        "event": "issues",
        "labels": [],
    }
    r.update(kw)
    return r


def _write(home: Path, unaccepted: list[dict]) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": unaccepted,
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )


def test_fr9821_held_digest_child_not_offered(home: Path):
    """Fail-when: child of held fr-digest must not be offered."""
    me = "marchhare-35600"
    digest = _row(
        9795,
        1,
        title="Digest: .NET fuel",
        labels=["feature-request", "fr-digest", "hold", "digest"],
        body="Kind: fr-digest\n",
    )
    child = _row(
        9803,
        2,
        title="FR-D: fuel cache",
        body="Depends-on: #9795\nImplement fuel cache.\n",
    )
    later = _row(9, 3, body="Depends-on: (none)\n")
    _write(home, [digest, child, later])
    fi.handle_focus_cmd(home, REPO)

    st, job = gitclaim.offer_focus_top(home, me, "#marchhare")
    assert st == "ok" and job is not None
    assert job["id"] == "#9"
    why = gitclaim.depends_gate_reason(child, gitclaim.load_queue(home))
    assert why == gitclaim.DEPENDS_HELD_REASON


def test_fr9821_unheld_digest_child_offered(home: Path):
    """Unhold releases children while digest stays OPEN."""
    me = "marchhare-35600"
    digest = _row(
        9795,
        1,
        title="Digest: .NET fuel",
        labels=["feature-request", "fr-digest", "digest"],
        body="Kind: fr-digest\n",
    )
    child = _row(
        9803,
        2,
        title="FR-D: fuel cache",
        body="Depends-on: #9795\nImplement fuel cache.\n",
    )
    _write(home, [digest, child])
    fi.handle_focus_cmd(home, REPO)

    st, job = gitclaim.offer_focus_top(home, me, "#marchhare")
    assert st == "ok" and job is not None
    assert job["id"] == "#9803"
    assert gitclaim.depends_gate_reason(child, gitclaim.load_queue(home)) is None


def test_fr9821_offerable_count_skips_held_digest_child(home: Path):
    digest = _row(
        9795,
        1,
        labels=["fr-digest", "hold", "digest"],
        body="Kind: fr-digest\n",
    )
    child = _row(9803, 2, body="Depends-on: #9795\n")
    later = _row(9, 3, body="Depends-on: (none)\n")
    rows = [digest, child, later]
    qdoc = {"v": 1, "unaccepted": rows, "accepted": [], "done": []}
    n = stuck_job_sweep.ungated_unaccepted_count(rows, doc=qdoc)
    # Digest itself is still a row but offer walks skip it; ungated count should
    # exclude the held-digest child and typically the digest gate row only when
    # other gates apply — child must not inflate offerable.
    assert n == 1  # only #9


def test_fr9821_list_omits_held_digest_child(home: Path):
    digest = _row(
        9795,
        1,
        labels=["fr-digest", "hold", "digest"],
        body="Kind: fr-digest\n",
        title="Digest: fuel",
    )
    child = _row(9803, 2, body="Depends-on: #9795\n", title="child of held")
    later = _row(9, 3, body="Depends-on: (none)\n", title="free FR")
    _write(home, [digest, child, later])
    lines = gitclaim.format_unaccepted_list(home)
    blob = "\n".join(lines)
    assert "9803" not in blob
    assert "#9" in blob or "free FR" in blob


def test_fr9821_enqueue_held_digest_as_gate_record():
    """Held fr-digest must enter unaccepted (not SKIP_FR-drop)."""
    doc = {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}}
    claim = gitclaim.GitClaim(
        repo=REPO,
        task="FR",
        id="#9795",
        event="issues",
        action="opened",
        line=f"FR {REPO}#9795",
        title="Digest: .NET fuel",
        body="Kind: fr-digest\n",
        labels=("feature-request", "fr-digest", "hold", "digest"),
        state="open",
    )
    ch = gitclaim._append_unaccepted(doc, claim)
    assert ch == "added"
    assert len(doc["unaccepted"]) == 1
    row = doc["unaccepted"][0]
    assert row["id"] == "#9795"
    assert gitclaim.digest_issue_reason(row)
    assert gitclaim.row_fr_hold_reason(row)


def test_fr9821_intake_digest_labels_include_hold():
    labs = intake._labels_for(
        {
            "kind": "fr",
            "title": "Digest: MONITORING keep-queue",
            "body": "Parent for child FRs.\n",
        },
        quarantine=False,
    )
    lower = {x.lower() for x in labs}
    assert "feature-request" in lower
    assert "fr-digest" in lower
    assert "digest" in lower
    assert "hold" in lower


def test_fr9821_intake_kind_stamp_gets_hold():
    labs = intake._labels_for(
        {
            "kind": "fr",
            "title": "Batch go-gate",
            "body": "Kind: fr-digest\n\nChildren wait for unhold.\n",
        },
        quarantine=False,
    )
    lower = {x.lower() for x in labs}
    assert "hold" in lower
    assert "fr-digest" in lower


def test_fr9821_ordinary_fr_not_forced_hold():
    labs = intake._labels_for(
        {
            "kind": "fr",
            "title": "Fix offer sticky pin",
            "body": "Depends-on: (none)\nOrdinary product FR.\n",
        },
        quarantine=False,
    )
    lower = {x.lower() for x in labs}
    assert "hold" not in lower
    assert "fr-digest" not in lower


def test_fr9821_fr_digest_gate_module_marker():
    assert (SCRIPTS / "fr_digest_gate.py").is_file()
    assert fr_digest_gate.bob_g1_skip_held_digest() == "bob_g1_skip_held_digest"
    assert fr_digest_gate.is_held_fr_digest(
        labels=["fr-digest", "hold"], body="Kind: fr-digest\n"
    )
    assert not fr_digest_gate.is_held_fr_digest(
        labels=["fr-digest"], body="Kind: fr-digest\n"
    )
