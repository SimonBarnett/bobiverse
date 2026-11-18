# -*- coding: utf-8 -*-
"""FR #8286: FINISH reviewed SHA prefers gh headRefOid over lagging worktree HEAD."""
from __future__ import annotations

import json
from pathlib import Path

import bob_worker as bw
import opencode_seat_contract as osc


class _Proc:
    def __init__(self, stdout: str = "", returncode: int = 0):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = ""


def _gh_run(state: str, head: str, merge: str = ""):
    def run(cmd, **kw):
        if cmd and cmd[0] == "gh" and "pr" in cmd and "view" in cmd:
            doc = {
                "state": state,
                "headRefOid": head,
                "mergeCommit": {"oid": merge} if merge else None,
            }
            return _Proc(json.dumps(doc))
        if cmd and cmd[0] == "git" and "rev-parse" in cmd:
            return _Proc("edba42c3c5322248f25335834de6d4f0aeea09ca\n")
        return _Proc("", 1)

    return run


def test_fr8286_prefers_gh_head_over_worktree(tmp_path: Path):
    tip = "b89d1d476aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    lag = "edba42c3c5322248f25335834de6d4f0aeea09ca"
    (tmp_path / ".bob").mkdir()
    (tmp_path / ".bob" / "reviewed-sha").write_text(lag + "\n", encoding="utf-8")
    sha, source, state = osc.finish_reviewed_sha(
        "MRB SimonBarnett/bobiverse#8266",
        tmp_path,
        run=_gh_run("OPEN", tip),
    )
    assert sha == tip
    assert source == "gh-headRefOid"
    assert state == "OPEN"
    assert sha != lag


def test_fr8286_merged_uses_head_or_merge_commit(tmp_path: Path):
    tip = "b89d1d476bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    merge = "e3e9e114fccccccccccccccccccccccccccccccc"
    sha, source, state = osc.finish_reviewed_sha(
        "MRB SimonBarnett/bobiverse#8266",
        tmp_path,
        run=_gh_run("MERGED", tip, merge),
    )
    assert state == "MERGED"
    assert sha == tip
    assert source == "gh-headRefOid"

    sha2, source2, state2 = osc.finish_reviewed_sha(
        "MRB SimonBarnett/bobiverse#8266",
        tmp_path,
        run=_gh_run("MERGED", "", merge),
    )
    assert state2 == "MERGED"
    assert sha2 == merge
    assert source2 == "gh-mergeCommit"


def test_fr8286_finish_prompt_merged_short_circuit(monkeypatch, tmp_path: Path):
    tip = "b89d1d476ddddddddddddddddddddddddddddddd"

    def fake_finish(job_key, directory="", *, run=None):
        return tip, "gh-headRefOid", "MERGED"

    monkeypatch.setattr(osc, "finish_reviewed_sha", fake_finish)
    monkeypatch.setattr(bw, "load_opencode_delivery", lambda: __import__("opencode_delivery"))
    # Ensure bob_worker imports our patched osc
    import importlib

    importlib.reload(bw)
    monkeypatch.setattr(
        "opencode_seat_contract.finish_reviewed_sha",
        fake_finish,
    )
    text = bw.opencode_job_finish_steps(
        job_key="MRB SimonBarnett/bobiverse#8266",
        worktree=str(tmp_path),
        outbox=str(tmp_path / "outbox.txt"),
    )
    assert "already MERGED" in text
    assert tip in text
    assert "lagging worktree HEAD" in text
    assert f"PASS @ {tip}" in text


def test_fr8286_finish_prompt_open_quotes_gh_tip(monkeypatch, tmp_path: Path):
    tip = "b89d1d476eeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"

    def fake_finish(job_key, directory="", *, run=None):
        return tip, "gh-headRefOid", "OPEN"

    monkeypatch.setattr("opencode_seat_contract.finish_reviewed_sha", fake_finish)
    text = bw.opencode_job_finish_steps(
        job_key="MRB SimonBarnett/bobiverse#8266",
        worktree=str(tmp_path),
        outbox=str(tmp_path / "outbox.txt"),
    )
    assert tip in text
    assert "gh pr view headRefOid" in text or "source=gh-headRefOid" in text
    assert f"MRB PASS @ {tip}" in text
