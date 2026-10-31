"""FR #4842: Cursor stale-replay assign + cross-job DONE + submit-verify job-key match."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import bob_worker as bw

ASSIGN_K = (
    "FROM Jeeves #marchhare marchhare-18680: FR SimonBarnett/bobiverse#4827 "
    "https://github.com/SimonBarnett/bobiverse/issues/4827"
)
ASSIGN_J = (
    "FROM Jeeves #marchhare marchhare-18680: MRB SimonBarnett/bobiverse#4836 "
    "https://github.com/SimonBarnett/bobiverse/pull/4836"
)
ACK_K = "ACK FR SimonBarnett/bobiverse#4827"
GIVEUP_K = "GIVEUP FR SimonBarnett/bobiverse#4827 cursor turn ended status=error"
ACK_J = "ACK MRB SimonBarnett/bobiverse#4836"
DONE_K = "DONE FR SimonBarnett/bobiverse#4827 https://github.com/SimonBarnett/bobiverse/pull/4840"
DONE_J = "DONE MRB SimonBarnett/bobiverse#4836 PASS https://github.com/SimonBarnett/bobiverse/pull/4836"


def _bored(logs=None, clock=None):
    logs = logs if logs is not None else []
    t = [100.0]

    def clk():
        return float(clock[0] if clock is not None else t[0])

    return bw.BoredEmitter(
        lambda: True,
        logs.append,
        clock=clk if clock is None else (lambda: float(clock[0])),
        harvest_hold_s=90.0,
        idle_s=9999.0,
        repeat_s=9999.0,
        retry_s=0.05,
        done_miss_grace_s=20.0,
    ), logs


def _write_transcript(path: Path, objs: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(o) for o in objs) + "\n", encoding="utf-8")
    return path


def _user_assign(text: str) -> dict:
    return {
        "role": "user",
        "message": {"content": [{"type": "text", "text": text}]},
    }


def test_transcript_latest_user_assign_key(tmp_path):
    tp = _write_transcript(
        tmp_path / "t.jsonl",
        [
            _user_assign("hello"),
            _user_assign(ASSIGN_K),
            {"role": "assistant", "message": {"content": [{"type": "text", "text": "working"}]}},
            _user_assign(ASSIGN_J),
        ],
    )
    assert bw.cursor_transcript_latest_user_assign_key(tp) == "MRB SimonBarnett/bobiverse#4836"


def test_stale_replay_key_when_finished_differs_from_open_ack():
    finished = {"FR SimonBarnett/bobiverse#4827"}
    assert (
        bw.stale_replay_assign_key(
            user_key="FR SimonBarnett/bobiverse#4827",
            finished_keys=finished,
            open_ack_key="MRB SimonBarnett/bobiverse#4836",
        )
        == "FR SimonBarnett/bobiverse#4827"
    )
    assert (
        bw.stale_replay_assign_key(
            user_key="MRB SimonBarnett/bobiverse#4836",
            finished_keys=finished,
            open_ack_key="MRB SimonBarnett/bobiverse#4836",
        )
        is None
    )
    assert (
        bw.stale_replay_assign_key(
            user_key="FR SimonBarnett/bobiverse#9999",
            finished_keys=finished,
            open_ack_key="MRB SimonBarnett/bobiverse#4836",
        )
        is None
    )


def test_giveup_then_stale_replay_user_turn_emits_stale_replay_giveup():
    """GIVEUP K, ACK J open, transcript user turn is K -> GIVEUP K stale-replay; keep ACK J."""
    logs: list[str] = []
    bored, _ = _bored(logs)
    bored.set_ready(True)
    bored.on_outbox(ACK_K)
    bored.on_outbox(GIVEUP_K)
    assert bored.ack_open is False
    bored.on_outbox(ACK_J)
    assert bored.ack_open is True
    assert bored._ack_job_key == "MRB SimonBarnett/bobiverse#4836"

    out: list[str] = []
    reinjected: list[str] = []
    hit = bored.note_stale_replay_user_assign(
        "FR SimonBarnett/bobiverse#4827",
        write_giveup=lambda s: out.append(s) or True,
        reinject_open=lambda: reinjected.append(bored._ack_job_key or "") or True,
    )
    assert hit == "FR SimonBarnett/bobiverse#4827"
    assert out == ["GIVEUP FR SimonBarnett/bobiverse#4827 stale-replay"]
    assert reinjected == ["MRB SimonBarnett/bobiverse#4836"]
    assert bored.ack_open is True
    assert bored._ack_job_key == "MRB SimonBarnett/bobiverse#4836"
    assert any("stale-replay" in m for m in logs)


def test_cross_job_done_arms_done_miss_for_open_ack():
    """DONE K while ACK J open: keep ACK J, arm done-miss for J (do not silent-drop only)."""
    clock = [100.0]
    logs: list[str] = []
    bored, _ = _bored(logs, clock=clock)
    bored.set_ready(True)
    bored.on_outbox(ACK_J)
    assert bored.ack_open is True
    bored.on_outbox(DONE_K)
    assert bored.ack_open is True
    assert bored._ack_job_key == "MRB SimonBarnett/bobiverse#4836"
    assert bored._done_miss_armed_at is not None
    assert bored._done_miss_key == "MRB SimonBarnett/bobiverse#4836"
    assert any("cross-job DONE" in m for m in logs)
    assert any("done-miss armed" in m for m in logs)


def test_cursor_probe_fails_when_newest_history_is_wrong_job(tmp_path):
    """submit-verify must match injected job key on the newest assign entry, not any older paste."""
    t0 = time.time()
    d = tmp_path / "ws" / "chat"
    d.mkdir(parents=True)
    f = d / "prompt_history.json"
    # Newest entry is the stale K assign; injected want is J.
    f.write_text(json.dumps([ASSIGN_J, ASSIGN_K]), encoding="utf-8")
    os.utime(f, (t0 + 1, t0 + 1))
    assert (
        bw.probe_cursor_prompt_history(tmp_path, ASSIGN_J, since_wall=t0, require_newest_job_key=True)
        is False
    )
    # Newest matches injected J.
    f.write_text(json.dumps([ASSIGN_K, ASSIGN_J]), encoding="utf-8")
    os.utime(f, (t0 + 2, t0 + 2))
    assert (
        bw.probe_cursor_prompt_history(tmp_path, ASSIGN_J, since_wall=t0, require_newest_job_key=True)
        is True
    )


def test_cursor_recovery_clears_input_before_repaste():
    cleared: list[str] = []
    pasted: list[str] = []

    def reinject(line, cb):
        pasted.append(line)
        return True

    rec = bw.InjectRecovery(
        reinject=reinject,
        write_outbox=lambda text: True,
        clear_local=lambda line: None,
        is_acked=lambda line: True,
        log=lambda m: None,
        giveup_on_fail=True,
        block_on_receipt_ack=False,
        turn_running=lambda: False,
        clear_input=lambda: cleared.append("cleared"),
    )
    assert rec.on_failed(ASSIGN_J, attempt=1) == "retried"
    assert cleared == ["cleared"], "FR #4842: clear queued input before re-paste"
    assert pasted == [ASSIGN_J]


# --- FR #5327: DONE K must not stale-replay GIVEUP / re-inject J ---


def test_fr5327_done_key_not_stale_replay_target():
    """DONE-finished K in transcript while ACK J open: no stale-replay hit."""
    finished = {"MRB SimonBarnett/agentic_fomprep#244"}
    done = {"MRB SimonBarnett/agentic_fomprep#244"}
    assert (
        bw.stale_replay_assign_key(
            user_key="MRB SimonBarnett/agentic_fomprep#244",
            finished_keys=finished,
            open_ack_key="MRB SimonBarnett/bobiverse#5297",
            done_keys=done,
        )
        is None
    )


def test_fr5327_giveup_finished_still_stale_replay():
    """GIVEUP-finished K (not DONE) while ACK J open: still stale-replay."""
    finished = {"FR SimonBarnett/bobiverse#4827"}
    done: set[str] = set()
    assert (
        bw.stale_replay_assign_key(
            user_key="FR SimonBarnett/bobiverse#4827",
            finished_keys=finished,
            open_ack_key="MRB SimonBarnett/bobiverse#4836",
            done_keys=done,
        )
        == "FR SimonBarnett/bobiverse#4827"
    )


def test_fr5327_done_k_transcript_lag_no_giveup_no_reinject():
    """DONE K, ACK J, transcript still K: no GIVEUP, no re-inject (one inject)."""
    logs: list[str] = []
    bored, _ = _bored(logs)
    bored.set_ready(True)
    bored.on_outbox(ACK_K)
    bored.on_outbox(DONE_K)
    assert "FR SimonBarnett/bobiverse#4827" in bored._finished_job_keys
    assert "FR SimonBarnett/bobiverse#4827" in bored._done_job_keys
    bored.on_outbox(ACK_J)
    assert bored.ack_open is True
    assert bored._ack_job_key == "MRB SimonBarnett/bobiverse#4836"

    out: list[str] = []
    reinjected: list[str] = []
    hit = bored.note_stale_replay_user_assign(
        "FR SimonBarnett/bobiverse#4827",
        write_giveup=lambda s: out.append(s) or True,
        reinject_open=lambda: reinjected.append(bored._ack_job_key or "") or True,
    )
    assert hit is None
    assert out == []
    assert reinjected == []
    assert bored.ack_open is True


def test_fr5327_giveup_path_not_in_done_keys():
    """GIVEUP marks finished but not done; stale-replay still hits."""
    logs: list[str] = []
    bored, _ = _bored(logs)
    bored.set_ready(True)
    bored.on_outbox(ACK_K)
    bored.on_outbox(GIVEUP_K)
    assert "FR SimonBarnett/bobiverse#4827" in bored._finished_job_keys
    assert "FR SimonBarnett/bobiverse#4827" not in bored._done_job_keys
    bored.on_outbox(ACK_J)
    out: list[str] = []
    hit = bored.note_stale_replay_user_assign(
        "FR SimonBarnett/bobiverse#4827",
        write_giveup=lambda s: out.append(s) or True,
        reinject_open=lambda: True,
    )
    assert hit == "FR SimonBarnett/bobiverse#4827"
    assert any("stale-replay" in x for x in out)


def test_mrb5400_skill_pins_fr5327_done_not_stale_replay():
    """docs/mrb-5400: worker skill must say DONE-finished K must not GIVEUP."""
    skill_path = (
        Path(__file__).resolve().parents[1]
        / ".grok"
        / "skills"
        / "bobiverse-bob-worker"
        / "SKILL.md"
    )
    text = skill_path.read_text(encoding="utf-8")
    assert "FR #4842 / #5327" in text
    assert "DONE-finished K" in text
    assert "must not GIVEUP or re-inject" in text
    assert "after GIVEUP/DONE for K" not in text
