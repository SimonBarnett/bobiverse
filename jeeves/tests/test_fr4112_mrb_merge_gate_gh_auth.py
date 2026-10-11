"""FR #4112: mrb_merge_gate _gh_token falls back to gh auth token when env unset."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

mrb_merge_gate = importlib.import_module("mrb_merge_gate")


def test_fr4112_gh_token_prefers_env(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "FAKE_env_token_parts")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    calls = []

    def boom():
        calls.append(1)
        raise AssertionError("gh auth must not run when env set")

    monkeypatch.setattr(mrb_merge_gate, "_gh_auth_token_cli", boom)
    assert mrb_merge_gate._gh_token() == "FAKE_env_token_parts"
    assert calls == []


def test_fr4112_gh_token_falls_back_to_gh_auth_cli(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(
        mrb_merge_gate, "_gh_auth_token_cli", lambda: "FAKE_cli_token_from_gh"
    )
    assert mrb_merge_gate._gh_token() == "FAKE_cli_token_from_gh"


def test_fr4112_gh_token_empty_when_env_and_cli_missing(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(mrb_merge_gate, "_gh_auth_token_cli", lambda: "")
    assert mrb_merge_gate._gh_token() == ""


def test_fr4112_fetch_error_mentions_gh_auth_fallback(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(mrb_merge_gate, "_gh_auth_token_cli", lambda: "")
    with pytest.raises(RuntimeError) as ei:
        mrb_merge_gate.fetch_issue_comments("SimonBarnett/bobiverse", "4112")
    msg = str(ei.value)
    assert "GH_TOKEN" in msg or "GITHUB_TOKEN" in msg
    assert "gh auth token" in msg.lower()


def test_fr4112_job_mrb_skill_mentions_gh_auth_fallback():
    skill = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
    raw = skill.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf"
    text = raw.decode("utf-8")
    assert "mrb_merge_gate.py" in text
    assert "gh auth token" in text.lower() or "GH_TOKEN" in text
