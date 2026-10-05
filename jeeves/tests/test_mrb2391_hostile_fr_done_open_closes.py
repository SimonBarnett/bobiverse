"""MRB #2391 hostile: open Closes-PR must not stick fr_done or eject desired (FR #2389)."""
from __future__ import annotations

from pathlib import Path

import gitclaim
from repo_layout import ROOT


def test_mrb2391_source_open_pr_loop_skips_closed_by_merged():
    text = (ROOT / "scripts" / "gitclaim.py").read_text(encoding="utf-8")
    assert "FR #2389" in text
    assert "closed_by_merged_pr" in text
    # Open-PR loop must not populate closed_by_merged_pr / supersede from Closes.
    # Find the open pulls iteration after uat_plan merged block.
    idx = text.index("# FR #2389: do NOT add open-PR Closes refs")
    window = text[idx : idx + 500]
    assert "closed_by_merged_pr.add" not in window
    assert "supersede_keys.add" not in window


def test_mrb2391_fr_done_clear_before_supersede_continue():
    text = (ROOT / "scripts" / "gitclaim.py").read_text(encoding="utf-8")
    # Clear stamp must be recorded before fr_is_superseded continue.
    clear = text.index("FR #2389 / #1201 / #1482: clear fr_done for every desired")
    supersede = text.index("fr_is_superseded(", clear)
    continue_idx = text.index("continue  # FR #254: MRB / open implement PR supersedes FR enqueue", supersede)
    assert clear < supersede < continue_idx


def test_mrb2391_merged_closer_fill_gated_on_repo_clear():
    """closed_by_merged_pr is filled only inside the repo_clear / UAT-cycle closed-pulls block."""
    text = (ROOT / "scripts" / "gitclaim.py").read_text(encoding="utf-8")
    gate = text.index("repo_clear[repo] = not blocking and not [p for p in prs if isinstance(p, dict)]")
    fill = text.index("# FR #2389: merged closers (recent cycle) remove issues from desired.")
    assert gate < fill
    # Open feature-request issues keep repo_clear False, so merged closers are not consulted
    # while GitHub still lists the FR open (normal: Closes merge already closed the issue).


def test_mrb2391_open_closes_keeps_issue_desired_path(tmp_path, monkeypatch):
    """Regression: open Closes alone must clear fr_done and queue MRB (product test twin)."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["ionos"]}', encoding="utf-8"
    )

    def _stamp(doc: dict) -> None:
        doc.setdefault("fr_done", {})["simonbarnett/bobiverse#7"] = gitclaim._utc_now()

    gitclaim._ledger_update(home, _stamp)
    issues = [
        {
            "number": 7,
            "title": "FR open",
            "body": "b",
            "state": "open",
            "labels": [{"name": "feature-request"}],
        }
    ]
    prs = [
        {
            "number": 8,
            "title": "PR for #7",
            "body": "Closes SimonBarnett/bobiverse#7\n",
            "state": "open",
            "html_url": "https://github.com/SimonBarnett/bobiverse/pull/8",
            "head": {"ref": "fr-7"},
            "base": {"ref": "main"},
            "user": {"login": "bob"},
        }
    ]

    def fake_fetch(url: str):
        if "/pulls" in url:
            return prs
        if "/issues" in url:
            return issues
        return []

    monkeypatch.setattr(gitclaim, "repo_archived_for_queue", lambda *a, **k: False)
    gitclaim.resync_from_github(
        home, ["SimonBarnett/bobiverse"], fetch_json=fake_fetch, token="x"
    )
    doc = gitclaim.load_queue(home)
    ids = [(r.get("task"), r.get("id")) for r in doc.get("unaccepted") or []]
    assert ("MRB", "#8") in ids
    assert ("FR", "#7") not in ids
    led = gitclaim.ledger_load(home)
    assert "simonbarnett/bobiverse#7" not in (led.get("fr_done") or {})


def test_mrb2391_files_end_with_newline():
    p = Path(__file__)
    assert p.read_bytes().endswith(b"\n")
    assert (ROOT / "scripts" / "gitclaim.py").read_bytes().endswith(b"\n")
