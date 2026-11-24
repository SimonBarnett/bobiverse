# -*- coding: utf-8 -*-
"""FR #9475: normalize_row_refs heals comma-strings and char-split lists."""
from __future__ import annotations

from pathlib import Path

import gitclaim


def test_fr9475_normalize_string_comma_joined():
    assert gitclaim.normalize_row_refs("#9270,#9442") == ["#9270", "#9442"]
    assert gitclaim.normalize_row_refs("#9270") == ["#9270"]
    assert gitclaim.normalize_row_refs("9270 9442") == ["#9270", "#9442"]


def test_fr9475_normalize_char_split_list():
    poisoned = ["#", "9", "2", "7", "0"]
    assert gitclaim.normalize_row_refs(poisoned) == ["#9270"]
    multi = list("#9270,#9442")
    assert gitclaim.normalize_row_refs(multi) == ["#9270", "#9442"]


def test_fr9475_normalize_good_list_unchanged():
    assert gitclaim.normalize_row_refs(["#9270", "#9442"]) == ["#9270", "#9442"]
    assert gitclaim.normalize_row_refs([]) == []
    assert gitclaim.normalize_row_refs(None) == []


def test_fr9475_row_refs_and_link_keys_use_normalize():
    row = {"repo": "SimonBarnett/bobiverse", "id": "#9452", "refs": "#9270"}
    assert gitclaim._row_refs(row) == ["#9270"]
    assert gitclaim._row_refs_list(row) == ["#9270"]
    keys = gitclaim._row_link_keys(row)
    assert "simonbarnett/bobiverse#9270" in keys
    assert "simonbarnett/bobiverse#" not in keys
    assert "simonbarnett/bobiverse#9" not in keys

    char_row = {
        "repo": "SimonBarnett/bobiverse",
        "id": "#9452",
        "refs": ["#", "9", "2", "7", "0"],
    }
    assert gitclaim._row_refs(char_row) == ["#9270"]
    keys2 = gitclaim._row_link_keys(char_row)
    assert "simonbarnett/bobiverse#9270" in keys2
    assert "simonbarnett/bobiverse#9" not in keys2


def test_fr9475_coerce_row_heals_and_clears_no_eligible():
    raw = {
        "repo": "SimonBarnett/bobiverse",
        "task": "MRB",
        "id": "#9452",
        "ts": "t0",
        "line": "https://github.com/SimonBarnett/bobiverse/pull/9452",
        "event": "pull_request",
        "action": "synchronize",
        "seq": 1,
        "refs": ["#", "9", "4", "5", "2"],
        "no_eligible_since": 1_700_000_000.0,
        "no_eligible_reported": True,
    }
    out = gitclaim._coerce_row(raw)
    assert out is not None
    assert out["refs"] == ["#9452"]
    assert "no_eligible_since" not in out
    assert "no_eligible_reported" not in out


def test_fr9475_coerce_string_refs_become_list():
    raw = {
        "repo": "SimonBarnett/bobiverse",
        "task": "MRB",
        "id": "#9464",
        "ts": "t0",
        "line": "x",
        "event": "pull_request",
        "action": "synchronize",
        "seq": 2,
        "refs": "#9460,#9458",
    }
    out = gitclaim._coerce_row(raw)
    assert out is not None
    assert out["refs"] == ["#9460", "#9458"]


def test_fr9475_ensure_mrb_requeue_reads_string_prior_refs(tmp_path: Path):
    """prior refs stored as comma-string must not char-split into fragment refs."""
    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "MRB",
                "id": "#9464",
                "ts": "t0",
                "line": "https://github.com/SimonBarnett/bobiverse/pull/9464",
                "event": "pull_request",
                "action": "opened",
                "seq": 1,
                "refs": "#9460",
                "title": "FR #9460 tip",
                "body": "Closes #9460",
            }
        ],
        "accepted": [],
        "done": [],
    }
    status = gitclaim.ensure_mrb_requeued_after_head_move(
        doc,
        tmp_path,
        repo="SimonBarnett/bobiverse",
        pr="9464",
        url="https://github.com/SimonBarnett/bobiverse/pull/9464",
        reason="synchronize",
        fetch_pr=False,
    )
    assert status in ("added", "duplicate", "noop", "updated", "skipped") or status
    # Find the MRB row and assert refs are not character fragments.
    rows = [
        r
        for r in (doc.get("unaccepted") or [])
        if isinstance(r, dict)
        and str(r.get("task") or "").upper() == "MRB"
        and str(r.get("id") or "") in ("#9464", "9464")
    ]
    assert rows, doc.get("unaccepted")
    refs = gitclaim.normalize_row_refs(rows[0].get("refs"))
    assert refs == ["#9460"]
    assert "#" not in refs
    assert "9" not in refs


def test_fr9475_synchronize_extra_refs_string_does_not_poison(tmp_path, monkeypatch):
    """extra['refs']=comma-join must not leave a string that later char-splits."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    doc = {"v": 1, "unaccepted": [], "accepted": [], "done": []}
    claim = gitclaim.GitClaim(
        repo="SimonBarnett/bobiverse",
        task="MRB",
        id="#9472",
        event="pull_request",
        action="opened",
        line="https://github.com/SimonBarnett/bobiverse/pull/9472",
        title="fix companion",
        body="Refs #9460",
        refs=("#9460",),
    )
    extra = {"refs": ",".join(claim.refs), "url": claim.line}
    changed = gitclaim._append_unaccepted(doc, claim, home=home, **extra)
    assert changed == "added"
    row = doc["unaccepted"][0]
    assert isinstance(row.get("refs"), list)
    assert row["refs"] == ["#9460"]
    # Refresh path (duplicate) with string extra must stay a list.
    claim2 = gitclaim.GitClaim(
        repo="SimonBarnett/bobiverse",
        task="MRB",
        id="#9472",
        event="pull_request",
        action="synchronize",
        line=claim.line,
        title="fix companion",
        body="Refs #9460",
        refs=("#9460", "#9458"),
    )
    extra2 = {"refs": ",".join(claim2.refs), "url": claim.line}
    changed2 = gitclaim._append_unaccepted(doc, claim2, home=home, **extra2)
    assert changed2 == "duplicate"
    row2 = doc["unaccepted"][0]
    assert isinstance(row2.get("refs"), list)
    assert row2["refs"] == ["#9460", "#9458"]
