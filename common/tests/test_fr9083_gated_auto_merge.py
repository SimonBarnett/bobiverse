# -*- coding: utf-8 -*-
"""FR #9083 / #8977: never gh pr merge after mrb_merge_gate refuses owner HOLD."""
from __future__ import annotations

from pathlib import Path

import importlib

import pytest

mrb_merge_gate = importlib.import_module("mrb_merge_gate")


def _pass_board() -> dict:
    return {
        "body": "## MRB board\n\n**Verdict:** PASS\nMRB PASS @ abc123\n",
        "created_at": "2026-11-22T20:00:00Z",
        "author_association": "OWNER",
        "user": {"login": "seat"},
    }


def _owner_hold() -> dict:
    return {
        "body": "HOLD: linked FR is phase-gated. Do not merge until FR hold is removed.",
        "created_at": "2026-11-21T12:00:00Z",
        "author_association": "OWNER",
        "user": {"login": "SimonBarnett"},
    }


def _stub_coderabbit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mrb_merge_gate,
        "resolve_coderabbit_row_for_pr",
        lambda *a, **k: {"coderabbit": "off"},
    )


def test_gated_auto_merge_refuses_hold_without_calling_gh(monkeypatch: pytest.MonkeyPatch):
    calls: list[list[str]] = []

    def fake_fetch(repo: str, num: str, *, token=None, **kwargs):
        return [_owner_hold(), _pass_board()]

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        raise AssertionError("gh must not run when gate refuses")

    _stub_coderabbit(monkeypatch)
    monkeypatch.setattr(mrb_merge_gate, "fetch_issue_comments", fake_fetch)
    monkeypatch.setattr(mrb_merge_gate.subprocess, "run", fake_run)

    code = mrb_merge_gate.gated_auto_merge("SimonBarnett/bobiverse", "8753")
    assert code == 2
    assert calls == []


def test_gated_auto_merge_runs_gh_when_gate_ok(monkeypatch: pytest.MonkeyPatch):
    calls: list[list[str]] = []

    def fake_fetch(repo: str, num: str, *, token=None, **kwargs):
        return [_pass_board()]

    class _Proc:
        returncode = 0
        stdout = "ok\n"
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return _Proc()

    _stub_coderabbit(monkeypatch)
    monkeypatch.setattr(mrb_merge_gate, "fetch_issue_comments", fake_fetch)
    monkeypatch.setattr(mrb_merge_gate.subprocess, "run", fake_run)

    code = mrb_merge_gate.gated_auto_merge("SimonBarnett/bobiverse", "8753")
    assert code == 0
    assert len(calls) == 1
    assert calls[0][:3] == ["gh", "pr", "merge"]
    assert "8753" in calls[0]
    assert "--auto" in calls[0]
    assert "--merge" in calls[0]
    assert "--repo" in calls[0]
    assert "SimonBarnett/bobiverse" in calls[0]


def test_main_merge_flag_refuses_without_gh(monkeypatch: pytest.MonkeyPatch, capsys):
    def fake_fetch(repo: str, num: str, *, token=None, **kwargs):
        return [_owner_hold(), _pass_board()]

    def fake_run(cmd, **kwargs):
        raise AssertionError("gh must not run")

    _stub_coderabbit(monkeypatch)
    monkeypatch.setattr(mrb_merge_gate, "fetch_issue_comments", fake_fetch)
    monkeypatch.setattr(mrb_merge_gate.subprocess, "run", fake_run)

    code = mrb_merge_gate.main(
        ["SimonBarnett/bobiverse", "8753", "--merge"]
    )
    assert code == 2
    err = capsys.readouterr().err
    assert "merge refused" in err or "owner hold" in err.lower()


def test_mrb_skill_pins_gated_auto_merge():
    """Skill book must prefer --merge / gated_auto_merge (FR #9083)."""
    root = Path(__file__).resolve().parents[2]
    skill = root / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
    body = skill.read_text(encoding="utf-8")
    assert "gated_auto_merge" in body
    assert "mrb_merge_gate.py <owner/repo> <pr> --merge" in body
    assert "Never** run a separate `gh pr merge` after a refused gate" in body or (
        "Never run a separate" in body and "refused gate" in body
    )
