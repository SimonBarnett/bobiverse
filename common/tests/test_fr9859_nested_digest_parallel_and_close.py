"""FR #9859: nested digest parallel offer + auto-close cascade/fixpoint."""
from __future__ import annotations

import sys
from pathlib import Path

import bobreport
import focus_ignore as fi
import gitclaim
import pytest
import registered_machines

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import fr_digest_auto_close as fac  # noqa: E402

REPO = "SimonBarnett/bobiverse"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"marchhare", "flamingo"})
    digest = bobreport.empty_digest()
    for mid, pids in (
        ("marchhare", ("35600", "35601", "35602")),
        ("flamingo", ("9",)),
    ):
        digest["machines"][mid] = bobreport._empty_machine(mid)
        digest["machines"][mid]["worker_list"] = [
            {
                "nick": f"{mid}-{p}",
                "state": "idle",
                "kind": "grok",
                "start_model": "grok-4",
                "configured_model": "grok-4",
                "updated": "2026-11-17T12:00:00Z",
            }
            for p in pids
        ]
    bobreport.save_digest(tmp_path, digest)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return tmp_path


def _row(repo: str, task: str, num: int, seq: int | None = None, **kw) -> dict:
    r = {
        "repo": repo,
        "task": task,
        "id": f"#{num}",
        "seq": seq if seq is not None else num + 1000,
        "ts": f"2026-10-01T10:00:{num:02d}Z",
        "line": f"{task} {repo}#{num}",
        "url": f"https://github.com/{repo}/{'pull' if task == 'MRB' else 'issues'}/{num}",
        "title": f"{task} {num}",
        "state": "open",
    }
    r.update(kw)
    return r


def _write(home: Path, *, unaccepted: list[dict], accepted: list[dict] | None = None) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": unaccepted,
            "accepted": list(accepted or []),
            "done": [],
            "workers": {},
        },
    )


def _issue(num: int, *, labels=(), state="open", body="", repo=REPO, **kw):
    row = {
        "number": num,
        "repo": repo,
        "state": state,
        "labels": [{"name": x} for x in labels],
        "body": body,
        "title": f"Issue {num}",
    }
    row.update(kw)
    return row


class IssueStore:
    """Mutable hermetic issue store keyed by (repo, number)."""

    def __init__(self) -> None:
        self.issues: dict[tuple[str, int], dict] = {}
        self.closes: list[tuple[str, int, str]] = []

    def put(self, issue: dict) -> dict:
        repo = str(issue.get("repo") or REPO)
        num = int(issue["number"])
        row = dict(issue)
        row["repo"] = repo
        self.issues[(repo.lower(), num)] = row
        return row

    def issue_open(self, repo: str, number) -> bool:
        key = (str(repo or "").lower(), int(str(number).lstrip("#")))
        if key not in self.issues:
            raise KeyError(key)
        st = str(self.issues[key].get("state") or "open").lower()
        return st in ("open", "opened")

    def fetch_issue(self, repo: str, number: int):
        key = (str(repo or "").lower(), int(number))
        if key not in self.issues:
            return None
        return dict(self.issues[key])

    def list_open_issues(self, repo: str):
        pref = str(repo or "").lower()
        return [
            dict(v)
            for (r, _n), v in sorted(self.issues.items())
            if r == pref and str(v.get("state") or "open").lower() in ("open", "opened")
        ]

    def close_issue(self, repo: str, number: int, comment: str) -> None:
        key = (str(repo or "").lower(), int(number))
        self.closes.append((str(repo), int(number), str(comment or "")))
        if key in self.issues:
            self.issues[key]["state"] = "closed"


def test_fr9859_parallel_children_both_offerable(home: Path):
    """S7: two digest-only children both offerable when digest unheld."""
    me1 = "marchhare-35600"
    me2 = "marchhare-35601"
    digest = _row(
        REPO,
        "FR",
        100,
        seq=1,
        title="Digest: parallel parent",
        labels=["feature-request", "fr-digest"],
        body="fr-digest batch unheld\n",
    )
    digest["nick"] = "flamingo-9"
    digest["accepted_ts"] = "2026-10-01T10:00:00Z"
    child_a = _row(REPO, "FR", 101, seq=2, body="Depends-on: #100\nA\n", title="child A")
    child_c = _row(REPO, "FR", 103, seq=3, body="Depends-on: #100\nC\n", title="child C")
    _write(home, unaccepted=[child_a, child_c], accepted=[digest])
    fi.handle_focus_cmd(home, REPO)

    doc = gitclaim.load_queue(home)
    assert gitclaim.depends_gate_reason(child_a, doc) is None
    assert gitclaim.depends_gate_reason(child_c, doc) is None

    # Digests are not work offers.
    assert gitclaim.row_is_digest_issue(digest)

    st1, job1 = gitclaim.offer_focus_top(home, me1, "#marchhare")
    assert st1 == "ok" and job1 is not None
    assert job1["id"] in ("#101", "#103")

    st2, job2 = gitclaim.offer_focus_top(home, me2, "#marchhare")
    assert st2 == "ok" and job2 is not None
    assert job2["id"] in ("#101", "#103")
    assert job1["id"] != job2["id"]

    doc2 = gitclaim.load_queue(home)
    offered = {
        r["id"]: str(r.get("offered_to") or "")
        for r in doc2["unaccepted"]
        if r.get("id") in ("#101", "#103")
    }
    assert offered["#101"] and offered["#103"]
    assert offered["#101"] != offered["#103"]


def test_fr9859_ordered_sibling_blocks_until_closed(home: Path):
    """Ordered pair Depends-on: #digest #sibling blocks until sibling CLOSED."""
    me = "marchhare-35600"
    digest = _row(
        REPO,
        "FR",
        200,
        seq=1,
        title="Digest: ordered",
        labels=["feature-request", "fr-digest"],
        body="fr-digest\n",
    )
    digest["nick"] = "flamingo-9"
    digest["accepted_ts"] = "2026-10-01T10:00:00Z"
    child_a = _row(REPO, "FR", 201, seq=2, body="Depends-on: #200\nA\n", title="A")
    child_b = _row(
        REPO,
        "FR",
        202,
        seq=3,
        body="Depends-on: #200 #201\nB after A\n",
        title="B",
    )
    _write(home, unaccepted=[child_a, child_b], accepted=[digest])
    fi.handle_focus_cmd(home, REPO)

    doc = gitclaim.load_queue(home)
    assert gitclaim.depends_gate_reason(child_a, doc) is None
    why_b = gitclaim.depends_gate_reason(child_b, doc)
    assert why_b == gitclaim.DEPENDS_OPEN_REASON

    st, job = gitclaim.offer_focus_top(home, me, "#marchhare")
    assert st == "ok" and job is not None
    assert job["id"] == "#201"

    # Accept A (move to accepted) - B still blocked while A open/accepted.
    doc = gitclaim.load_queue(home)
    unacc = [r for r in doc["unaccepted"] if r.get("id") != "#201"]
    accepted = list(doc.get("accepted") or []) + [
        next(r for r in doc["unaccepted"] if r.get("id") == "#201")
    ]
    accepted[-1]["nick"] = me
    accepted[-1]["accepted_ts"] = "2026-10-01T11:00:00Z"
    _write(home, unaccepted=unacc, accepted=[digest] + [accepted[-1]])

    doc = gitclaim.load_queue(home)
    child_b2 = next(r for r in doc["unaccepted"] if r.get("id") == "#202")
    assert gitclaim.depends_gate_reason(child_b2, doc) == gitclaim.DEPENDS_OPEN_REASON

    # Close A in queue view (state=closed) -> B offerable.
    a_row = next(r for r in doc["accepted"] if r.get("id") == "#201")
    a_row["state"] = "closed"
    gitclaim._write_queue(gitclaim.queue_path(home), doc)
    doc = gitclaim.load_queue(home)
    child_b3 = next(r for r in doc["unaccepted"] if r.get("id") == "#202")
    assert gitclaim.depends_gate_reason(child_b3, doc) is None

    st2, job2 = gitclaim.offer_focus_top(home, "marchhare-35601", "#marchhare")
    assert st2 == "ok" and job2 is not None
    assert job2["id"] == "#202"


def test_fr9859_nested_cascade_closes_phase_and_root_same_call():
    """Last leaf closes phase; same call closes root (FR #9552 nested)."""
    store = IssueStore()
    root = store.put(
        _issue(10, labels=("fr-digest", "digest"), body="Root digest\n")
    )
    phase = store.put(
        _issue(20, labels=("fr-digest",), body="Depends-on: #10\nPhase\n")
    )
    leaf = store.put(_issue(30, body="Depends-on: #20\nLeaf\n"))
    # Open list still shows leaf + phase + root (stale leaf is excluded by key).
    results = fac.maybe_close_fr_digest_parents(
        child_repo=REPO,
        child_number=30,
        child_body=leaf["body"],
        fetch_issue=store.fetch_issue,
        list_open_issues=store.list_open_issues,
        close_issue=store.close_issue,
    )
    actions = [(r["number"], r["action"]) for r in results]
    assert (20, "closed") in actions
    assert (10, "closed") in actions
    closed_nums = [n for _r, n, _c in store.closes]
    assert closed_nums == [20, 10] or (20 in closed_nums and 10 in closed_nums)
    # Order: phase before root.
    assert closed_nums.index(20) < closed_nums.index(10)


def test_fr9859_nested_cascade_held_phase_stops():
    """Held phase is skipped; no auto-unhold; root not cascaded from held."""
    store = IssueStore()
    store.put(_issue(10, labels=("fr-digest",), body="Root\n"))
    store.put(_issue(20, labels=("fr-digest", "hold"), body="Depends-on: #10\n"))
    leaf = store.put(_issue(30, body="Depends-on: #20\n"))
    results = fac.maybe_close_fr_digest_parents(
        child_repo=REPO,
        child_number=30,
        child_body=leaf["body"],
        fetch_issue=store.fetch_issue,
        list_open_issues=store.list_open_issues,
        close_issue=store.close_issue,
    )
    assert results[0]["action"] == "skipped_held"
    assert store.closes == []


def test_fr9859_reconcile_fixpoint_closes_root_same_call():
    """Stale snapshot with phase+root: one reconcile closes both (fail-when fixed)."""
    store = IssueStore()
    root = store.put(_issue(10, labels=("fr-digest",), body="Root\n"))
    phase = store.put(
        _issue(20, labels=("fr-digest",), body="Depends-on: #10\nPhase\n")
    )
    # No open leaf children remain - only digests in the open list.
    results = fac.reconcile_open_fr_digests(
        REPO,
        list_open_digest_issues=lambda r: [
            i for i in store.list_open_issues(r) if fac.is_fr_digest_issue(i)
        ],
        list_open_issues=store.list_open_issues,
        close_issue=store.close_issue,
        fetch_issue=store.fetch_issue,
    )
    by_num = {r["number"]: r["action"] for r in results}
    assert by_num[20] == "closed"
    assert by_num[10] == "closed"
    assert {n for _r, n, _c in store.closes} == {20, 10}


def test_fr9859_reconcile_unheld_root_zero_children():
    store = IssueStore()
    store.put(_issue(55, labels=("fr-digest",), body="orphan root\n"))
    results = fac.reconcile_open_fr_digests(
        REPO,
        list_open_digest_issues=lambda r: store.list_open_issues(r),
        list_open_issues=store.list_open_issues,
        close_issue=store.close_issue,
    )
    assert results[0]["action"] == "closed"
    assert store.closes[0][1] == 55


def test_fr9859_cascade_cycle_guard():
    """Mutual Depends-on digests must terminate (visited set)."""
    store = IssueStore()
    store.put(_issue(1, labels=("fr-digest",), body="Depends-on: #2\n"))
    store.put(_issue(2, labels=("fr-digest",), body="Depends-on: #1\n"))
    leaf = store.put(_issue(3, body="Depends-on: #1\n"))
    # #2 Depends-on #1 so #2 is an open child of #1 -> skip.
    results = fac.maybe_close_fr_digest_parents(
        child_repo=REPO,
        child_number=3,
        child_body=leaf["body"],
        fetch_issue=store.fetch_issue,
        list_open_issues=store.list_open_issues,
        close_issue=store.close_issue,
    )
    assert results
    assert results[0]["action"] == "skipped_open_children"

    # Close sibling leaf #3 and peer digest #2 so #1 has no open children.
    # Cascade from a fresh leaf onto #1; #1 body Depends-on #2 (already closed)
    # must not loop forever when evaluating ancestors.
    store.issues[(REPO.lower(), 3)]["state"] = "closed"
    store.issues[(REPO.lower(), 2)]["state"] = "closed"
    leaf2 = store.put(_issue(4, body="Depends-on: #1\n"))
    results2 = fac.maybe_close_fr_digest_parents(
        child_repo=REPO,
        child_number=4,
        child_body=leaf2["body"],
        fetch_issue=store.fetch_issue,
        list_open_issues=store.list_open_issues,
        close_issue=store.close_issue,
    )
    assert any(r.get("number") == 1 and r.get("action") == "closed" for r in results2)
    # Cascade may visit #2 (already closed) -> skipped_already_closed; finite.
    assert len(results2) <= 4
    assert len(results2) >= 1


def test_fr9859_marker():
    assert fac.bob_fr9552_auto_close_digest is True
