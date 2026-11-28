"""FR #9665: GIVEUP depends_open stamps durable block; soft-allow digests still skip re-offer."""
from __future__ import annotations

from pathlib import Path

import gitclaim
import shop_listen

REPO = "SimonBarnett/bobiverse"


def test_parse_depends_open_structured_reason():
    assert gitclaim.parse_blocked_depends_giveup_refs(
        "depends_open:#9653", home_repo=REPO
    ) == [(REPO, 9653)]
    assert gitclaim.parse_blocked_depends_giveup_refs(
        "reason=depends_open:#9653 digest still open", home_repo=REPO
    ) == [(REPO, 9653)]
    assert gitclaim.parse_blocked_depends_giveup_refs(
        "depends_open=SimonBarnett/bobiverse#9653", home_repo=REPO
    ) == [(REPO, 9653)]
    # Legacy blocked:depends-on still works.
    assert gitclaim.parse_blocked_depends_giveup_refs(
        "blocked:depends-on #9354", home_repo=REPO
    ) == [(REPO, 9354)]
    assert gitclaim.parse_blocked_depends_giveup_refs("out of fuel", home_repo=REPO) == []


def test_apply_stamps_depends_open_field():
    row = {
        "task": "FR",
        "repo": REPO,
        "id": "#9622",
        "body": "Depends-on: #9653\nchair work\n",
        "labels": ["feature-request"],
    }
    refs = gitclaim.apply_depends_on_giveup_stamp(
        row, "depends_open:#9653", patch_github=False
    )
    assert refs == [(REPO, 9653)]
    assert row.get("depends_open") == ["#9653"]
    assert "Depends-on: #9653" in str(row.get("body") or "")


def test_depends_open_block_bypasses_unheld_digest_soft_allow():
    """Unheld fr-digest soft-allow must not re-offer after depends_open GIVEUP stamp."""
    digest = {
        "task": "FR",
        "repo": REPO,
        "id": "#9653",
        "title": "Digest: MONITORING keep-queue",
        "body": "Children...\n",
        "labels": ["feature-request", "fr-digest"],
    }
    child = {
        "task": "FR",
        "repo": REPO,
        "id": "#9622",
        "title": "chair: false self-MRB",
        "body": "Depends-on: #9653\n",
        "labels": ["feature-request", "needs-walrus"],
        "depends_open": ["#9653"],
    }
    doc = {"unaccepted": [digest, child], "accepted": [], "done": []}
    open_keys = {(REPO, 9653), (REPO, 9622)}
    # FR #10059: unheld OPEN digest blocks even without a depends_open stamp.
    soft = dict(child)
    soft.pop("depends_open", None)
    assert (
        gitclaim.row_depends_open_reason(soft, open_keys, doc=doc)
        == gitclaim.DEPENDS_OPEN_REASON
    )
    # With depends_open stamp: hard block.
    why = gitclaim.row_depends_open_reason(child, open_keys, doc=doc)
    assert why == gitclaim.DEPENDS_OPEN_REASON
    assert gitclaim.depends_gate_reason(child, doc=doc, open_keys=open_keys) == (
        gitclaim.DEPENDS_OPEN_REASON
    )


def test_depends_open_clears_when_depend_closed():
    row = {
        "task": "FR",
        "repo": REPO,
        "id": "#9622",
        "body": "Depends-on: #9653\n",
        "labels": [],
        "depends_open": ["#9653"],
    }
    # FR #10059: no checker and the depend is not positively closed => unresolved.
    why = gitclaim.row_depends_open_reason(row, set(), doc={"unaccepted": [row]})
    assert why == gitclaim.DEPENDS_UNRESOLVED_REASON


def test_shop_giveup_depends_open_skips_reoffer(tmp_path: Path, monkeypatch):
    home = tmp_path / "chair"
    home.mkdir()
    digest = {
        "task": "FR",
        "repo": REPO,
        "id": "#9653",
        "seq": 1,
        "title": "Digest parent",
        "body": "batch\n",
        "labels": ["fr-digest", "feature-request"],
    }
    child = {
        "task": "FR",
        "repo": REPO,
        "id": "#9622",
        "seq": 2,
        "title": "child",
        "body": "Depends-on: #9653\n",
        "labels": ["feature-request"],
        "nick": "redqueen-1",
        "accepted_by": "redqueen-1",
        "accepted_ts": "2026-11-24T14:00:00Z",
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [digest], "accepted": [child], "done": []},
    )
    _orig = gitclaim.apply_depends_on_giveup_stamp

    def _stamp_no_gh(row, reason, **_kw):
        return _orig(row, reason, patch_github=False)

    monkeypatch.setattr(gitclaim, "apply_depends_on_giveup_stamp", _stamp_no_gh)

    status, job = shop_listen.return_job_to_unaccepted(
        home,
        repo=REPO,
        task="FR",
        ident="#9622",
        now=1_700_000_000.0,
        reason="depends_open:#9653",
        expected_nick="redqueen-1",
    )
    assert status == "ok"
    assert job is not None
    assert job.get("depends_open") == ["#9653"]
    doc = gitclaim.load_queue(home)
    stamped = None
    for row in doc.get("unaccepted") or []:
        if str(row.get("id")) in ("#9622", "9622"):
            stamped = row
            break
    assert stamped is not None
    open_keys = {(REPO, 9653), (REPO, 9622)}
    assert gitclaim.depends_gate_reason(stamped, doc=doc, open_keys=open_keys) == (
        gitclaim.DEPENDS_OPEN_REASON
    )
