"""FR #9461: intervene_assign ear-relay !assign on idle+offerable."""
from __future__ import annotations

import sys
from pathlib import Path

MON = Path(__file__).resolve().parents[1] / "tools" / "monitor"
sys.path.insert(0, str(MON))

import intervene_assign as ia  # noqa: E402


def _fixture_idle_offerable():
    return {
        "ok": False,
        "idle_seats": [
            {"machine": "flamingo", "nick": "flamingo-17160", "pid": 17160, "state": "idle"},
            {"machine": "flamingo", "nick": "flamingo-17068", "pid": 17068, "state": "idle"},
        ],
        "offerable_for_live_seats": 2,
        "unaccepted": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "MRB",
                "id": "#9449",
                "mergeable": True,
                "mergeable_state": "CLEAN",
                "title": "MRB clean",
            },
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#9001",
                "title": "FR work",
            },
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "MRB",
                "id": "#8000",
                "needs_human": True,
                "title": "needs human",
            },
        ],
    }


def test_fr9461_idle_offerable_writes_privmsg(tmp_path):
    report = _fixture_idle_offerable()
    outbox = tmp_path / "outbox.txt"
    sleeps: list[float] = []

    def _sleep(s: float) -> None:
        sleeps.append(s)

    payload = ia.intervene_from_report(
        report,
        outbox=outbox,
        dry_run=False,
        pace_s=3.0,
        sleeper=_sleep,
        offerable_fn=lambda row, nick: True,
    )
    assert payload["written_count"] == 2
    text = outbox.read_bytes()
    assert not text.startswith(b"\xef\xbb\xbf")
    lines = outbox.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("PRIVMSG #bobiverse :!assign flamingo-")
    assert "MRB 9449" in lines[0]
    assert "FR 9001" in lines[1]
    assert sleeps == [3.0]
    assert all("8000" not in ln for ln in lines)


def test_fr9461_busy_seats_write_none(tmp_path):
    report = {
        "idle_seats": [
            {"machine": "flamingo", "nick": "flamingo-1", "pid": 1, "state": "doing"},
        ],
        "unaccepted": [
            {"repo": "SimonBarnett/bobiverse", "task": "FR", "id": "#1"},
        ],
        "offerable_for_live_seats": 1,
    }
    outbox = tmp_path / "outbox.txt"
    payload = ia.intervene_from_report(
        report,
        outbox=outbox,
        dry_run=False,
        pace_s=0,
        offerable_fn=lambda row, nick: True,
    )
    assert payload["written_count"] == 0
    assert not outbox.exists() or outbox.read_text(encoding="utf-8") == ""


def test_fr9461_self_mrb_skipped(tmp_path):
    report = {
        "idle_seats": [
            {"machine": "flamingo", "nick": "flamingo-99", "pid": 99, "state": "idle"},
        ],
        "unaccepted": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "MRB",
                "id": "#42",
                "pr_author": "flamingo-99",
                "mergeable": True,
            }
        ],
        "offerable_for_live_seats": 1,
    }
    outbox = tmp_path / "outbox.txt"
    payload = ia.intervene_from_report(
        report,
        outbox=outbox,
        dry_run=False,
        pace_s=0,
        offerable_fn=lambda row, nick: True,
    )
    assert payload["written_count"] == 0
    assert payload["planned"] == []


def test_fr9461_dry_run_no_write(tmp_path):
    report = _fixture_idle_offerable()
    outbox = tmp_path / "outbox.txt"
    payload = ia.intervene_from_report(
        report,
        outbox=outbox,
        dry_run=True,
        pace_s=3.0,
        offerable_fn=lambda row, nick: True,
    )
    assert payload["written_count"] == 2
    assert payload["dry_run"] is True
    assert not outbox.exists()


def test_fr9461_truncate_when_pos_eof(tmp_path):
    outbox = tmp_path / "outbox.txt"
    outbox.write_text("PRIVMSG #bobiverse :!assign x y FR 1\n", encoding="utf-8")
    pos = tmp_path / "outbox.txt.pos"
    pos.write_text(str(outbox.stat().st_size), encoding="utf-8")
    result = ia.truncate_drained_outbox(outbox, pos)
    assert result["truncated"] is True
    assert outbox.read_bytes() == b""


def test_fr9461_assign_line_format():
    assert (
        ia.assign_line("flamingo-1", "SimonBarnett/bobiverse", "MRB", "9446")
        == "PRIVMSG #bobiverse :!assign flamingo-1 SimonBarnett/bobiverse MRB 9446"
    )

def test_fr9461_cli_intervene_dry_run_with_fixture(tmp_path):
    """Wrapper DryRun must use --intervene-dry-run; --dry-run alone early-exits empty."""
    import json
    import subprocess

    fixture = tmp_path / 'report.json'
    fixture.write_text(json.dumps(_fixture_idle_offerable()), encoding='utf-8')
    outbox = tmp_path / 'outbox.txt'
    py = MON / 'intervene_assign.py'
    proc = subprocess.run(
        [
            sys.executable,
            str(py),
            '--fixture', str(fixture),
            '--ear-outbox', str(outbox),
            '--intervene-dry-run',
            '--allow-fast-pace',
            '--pace-s', '0',
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload.get('dry_run') is True
    assert payload.get('written_count', 0) == 2
    assert not outbox.exists()

