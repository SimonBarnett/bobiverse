"""FR #2790: harvest source.seat comes from bob-worker seat env (BOB_NICK).

PR #2759 made Jeeves take lesson-PR author from the intake footer ``seat=``.
``Invoke-BobiverseHarvest.ps1`` only read ``$env:BOB_AGENT_NICK``, but
``bob_worker.seat_env_extra`` only set ``BOB_NICK``. Live seats therefore
harvested with empty ``seat=``, and Jeeves could offer the opener its own
lesson MRB.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HARVEST_PS1 = ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"
NICK = "marchhare-31808"
MACHINE = "marchhare"

WIN = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("powershell"),
    reason="needs Windows PowerShell",
)


def _import_bob_worker():
    scripts = ROOT / "bob" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import bob_worker as bw  # noqa: WPS433

    return bw


def _harvest_dry_run(env: dict) -> dict:
    """Run Invoke-BobiverseHarvest -DryRun and parse the JSON payload."""
    merged = os.environ.copy()
    # Clear nick vars first so only the caller's seat env counts.
    merged.pop("BOB_NICK", None)
    merged.pop("BOB_AGENT_NICK", None)
    merged.update({k: str(v) for k, v in env.items() if v is not None})
    for dead in [k for k, v in list(merged.items()) if v == ""]:
        # Empty string means "unset" for this harness.
        merged.pop(dead, None)
    run = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(HARVEST_PS1),
            "-Repo",
            "SimonBarnett/bobiverse",
            "-Summary",
            "fr2790 seat stamp",
            "-Lesson",
            "seat nick must reach harvest source.seat",
            "-DryRun",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env=merged,
        cwd=str(ROOT),
    )
    assert run.returncode == 0, run.stdout + "\n" + run.stderr
    text = (run.stdout or "") + "\n" + (run.stderr or "")
    start = text.find("{")
    end = text.rfind("}")
    assert start >= 0 and end > start, text[-2000:]
    payload = json.loads(text[start : end + 1])
    return payload


def test_seat_env_extra_exports_bob_agent_nick_alias(tmp_path: Path):
    """Shared launch path must export the name harvest historically read."""
    bw = _import_bob_worker()
    run = tmp_path / f"worker-{NICK}-deadbeef"
    env = bw.seat_env_extra(run, MACHINE, NICK)
    assert env["BOB_NICK"] == NICK
    assert env["BOB_AGENT_NICK"] == NICK
    assert env["BOB_MACHINE"] == MACHINE


def test_agent_child_launch_exports_agent_nick_alias(tmp_path: Path):
    bw = _import_bob_worker()
    cwd = tmp_path / "worker"
    cwd.mkdir()
    (cwd / ".grok" / "skills").mkdir(parents=True)
    run_dir = tmp_path / "run" / "worker-x"
    run_dir.mkdir(parents=True)
    child = bw.describe_agent_child_launch(
        kind="grok",
        mode="agent",
        cwd=str(cwd),
        run_dir=run_dir,
        machine=MACHINE,
        nick=NICK,
        agent_exe=r"C:\fake\agent.exe",
    )
    assert child["env"]["BOB_NICK"] == NICK
    assert child["env"]["BOB_AGENT_NICK"] == NICK


@WIN
def test_harvest_dryrun_seat_from_seat_env_extra(tmp_path: Path):
    """Deterministic: seat env as bob_worker builds it -> harvest source.seat == nick."""
    bw = _import_bob_worker()
    run = tmp_path / f"worker-{NICK}-ac2cf015"
    run.mkdir(parents=True)
    (run / "outbox.txt").write_text("", encoding="utf-8")
    env = bw.seat_env_extra(run, MACHINE, NICK)
    # Prove the mismatch that #2759 left open: only BOB_NICK is enough once fixed.
    only_nick = {"BOB_NICK": env["BOB_NICK"], "BOB_AGENT_NICK": ""}
    payload = _harvest_dry_run(only_nick)
    assert payload["source"]["seat"] == NICK, payload["source"]


@WIN
def test_harvest_dryrun_seat_from_legacy_bob_agent_nick():
    """Watch-AgentHealth / legacy path still stamps seat via BOB_AGENT_NICK."""
    payload = _harvest_dry_run({"BOB_NICK": "", "BOB_AGENT_NICK": NICK})
    assert payload["source"]["seat"] == NICK, payload["source"]


@WIN
def test_harvest_dryrun_prefers_bob_nick_over_stale_agent_nick():
    payload = _harvest_dry_run(
        {"BOB_NICK": NICK, "BOB_AGENT_NICK": "stale-watch-seat-1"}
    )
    assert payload["source"]["seat"] == NICK, payload["source"]


def test_lesson_footer_seat_blocks_opener_from_own_mrb(tmp_path: Path):
    """End-to-end chair rule: footer seat=X => author_seat=X => X is self-MRB blocked."""
    sys.path.insert(0, str(ROOT / "common" / "scripts"))
    import bobreport  # noqa: WPS433
    import gitclaim  # noqa: WPS433

    # Seat nick parse for marchhare-* (same shape as live shop).
    def _parse(n):
        s = str(n or "")
        if s.lower().startswith("marchhare-") and s.rsplit("-", 1)[-1].isdigit():
            return ("marchhare", s.rsplit("-", 1)[-1])
        return None

    # Patch via monkeypatch-like setattr for this module-scoped helper.
    orig = bobreport.parse_seat_nick
    bobreport.parse_seat_nick = _parse
    try:
        home = tmp_path
        body = (
            "Session summary:\nlesson\n\nLessons:\n- x\n---\n"
            f"_source machine=`{MACHINE}` agent=`Invoke-BobiverseHarvest` "
            f"book=`harvest` ver=`-` seat=`{NICK}`_\n"
        )
        claim = gitclaim.claim_from_payload(
            "pull_request",
            {
                "action": "opened",
                "repository": {"full_name": "SimonBarnett/bobiverse"},
                "pull_request": {
                    "number": 2799,
                    "title": "lesson(harvest): seat stamp",
                    "body": body,
                    "draft": False,
                    "html_url": "https://github.com/SimonBarnett/bobiverse/pull/2799",
                    "labels": [{"name": "harvest-lesson"}],
                },
            },
        )
        assert claim is not None
        assert claim.opened_by == NICK
        gitclaim.apply_queue_event(home, claim)
        row = next(
            r
            for r in gitclaim._load_queue_unlocked(home)["unaccepted"]
            if r.get("id") == "#2799"
        )
        assert NICK in gitclaim.row_author_seats(row)
        live = {NICK, "ionos-1"}
        # Exact-seat self-MRB block (FR #2604): opener never gets its own lesson MRB.
        assert gitclaim.review_blocked_for_author(row, NICK, live) is True
        assert gitclaim.review_blocked_for_author(row, "ionos-1", live) is False
    finally:
        bobreport.parse_seat_nick = orig
