"""FR #8977: merge-gate exit 2 must not call gh pr merge."""
from __future__ import annotations

import mrb_merge_gate as gate


def test_finish_merge_skips_gh_on_exit_2():
    calls: list[list[str]] = []

    def run(cmd):
        calls.append(list(cmd))
        return 0

    assert gate.finish_merge(2, "SimonBarnett/bobiverse", "8742", run=run) == 2
    assert gate.finish_merge(3, "SimonBarnett/bobiverse", "8742", run=run) == 3
    assert calls == []


def test_finish_merge_calls_gh_only_after_zero():
    calls: list[list[str]] = []

    def run(cmd):
        calls.append(list(cmd))
        return 0

    assert gate.finish_merge(0, "SimonBarnett/bobiverse", "8742", run=run) == 0
    assert calls == [["gh", "pr", "merge", "8742", "--repo", "SimonBarnett/bobiverse", "--auto", "--merge"]]


def test_main_merge_flag_hard_stops(monkeypatch):
    def refuse(repo, num, token=None):
        raise RuntimeError("FR #3928 merge refused for %s#%s: owner hold active" % (repo, num))

    monkeypatch.setattr(gate, "assert_mrb_merge_allowed", refuse)
    calls: list[list[str]] = []
    monkeypatch.setattr(gate, "invoke_gh_pr_merge", lambda *a, **k: calls.append(list(a)) or 0)
    assert gate.main(["SimonBarnett/bobiverse", "8742", "--merge"]) == 2
    assert calls == []


def test_skill_says_exit_2_is_a_hard_stop():
    from pathlib import Path

    text = Path(__file__).resolve().parents[2].joinpath(
        "bob", ".grok", "skills", "bobiverse-bob-job-mrb", "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "FR #8977" in text
    assert "exit 2 is a hard stop" in text
    assert "mrb_merge_gate.py <owner/repo> <pr> --merge" in text
