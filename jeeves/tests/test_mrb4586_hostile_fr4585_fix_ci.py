"""MRB #4586 hostile pins for FR #4585 FIX CI offer."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

mrb_merge_on_green = importlib.import_module("mrb_merge_on_green")
gitclaim = importlib.import_module("gitclaim")

REPO = "SimonBarnett/a-search"
PASS_SHA = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def test_failure_signature_omits_pr_number():
    # FR #4596: PR number omitted only when collapsing for main_red.
    sig = mrb_merge_on_green.failure_signature(
        REPO, detail="test-and-synth failure", pr="1796", main_red=True
    )
    assert "1796" not in sig
    assert "|" in sig
    assert "test-and-synth" in sig or "failure" in sig


def test_resolve_assign_url_fix_uses_pull_url():
    row = {
        "task": "FIX",
        "repo": REPO,
        "id": "#1796",
        "url": f"https://github.com/{REPO}/pull/1796",
    }
    assert gitclaim.resolve_assign_url(row) == f"https://github.com/{REPO}/pull/1796"
    assert gitclaim._canon_task(row) == "FIX"


def test_enqueue_fix_ci_ledger_blocks_second_call(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    # Shared collapse still applies when main itself is red (FR #4585 / #4596).
    first = mrb_merge_on_green.enqueue_fix_ci(
        home,
        repo=REPO,
        pr="1796",
        pass_sha=PASS_SHA,
        detail="failure",
        main_red=True,
        now_epoch=1_000.0,
    )
    assert first == "added"
    second = mrb_merge_on_green.enqueue_fix_ci(
        home,
        repo=REPO,
        pr="1800",
        pass_sha=PASS_SHA,
        detail="failure",
        main_red=True,
        now_epoch=1_060.0,
    )
    assert second == "duplicate"
    q = gitclaim.load_queue(home)
    fixes = [
        r
        for r in (q.get("unaccepted") or [])
        if isinstance(r, dict) and str(r.get("task") or "").upper() == "FIX"
    ]
    assert len(fixes) == 1
