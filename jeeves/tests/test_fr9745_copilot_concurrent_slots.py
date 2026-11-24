"""FR #9745: Copilot concurrent slot cap 2."""
from __future__ import annotations

import time
from pathlib import Path

import copilot_dispatch as cd
import focus_ignore as fi
import gitclaim
import shop_listen


REPO = "SimonBarnett/bobiverse"


def _row(task="FR", num=10, **extra):
    row = {
        "repo": REPO,
        "task": task,
        "id": f"#{num}",
        "url": f"https://github.com/{REPO}/issues/{num}",
        "title": "do the thing",
    }
    row.update(extra)
    return row


def _mock_post_dispatch(response_base=None):
    """Create a mock post function that returns a successful dispatch response."""
    if response_base is None:
        response_base = {}

    call_count = [0]

    def mock_post(path, body):
        call_count[0] += 1
        result = {
            "status": 201,
            "id": f"task-{call_count[0]}",
            "state": "queued",
        }
        result.update(response_base)
        return result

    mock_post.call_count = call_count
    return mock_post


def test_max_concurrent_constant_is_two():
    """Verify MAX_CONCURRENT_COPILOT is set to 2."""
    assert cd.MAX_CONCURRENT_COPILOT == 2


def test_tick_dispatches_up_to_two_concurrent(tmp_path):
    """Test that tick() fills up to 2 concurrent slots and stops at 2."""
    fi.handle_focus_cmd(tmp_path, f"high {REPO}")
    cd.set_allowance(tmp_path, remaining=10)

    # Create 3 high-priority rows
    for num in [10, 11, 12]:
        claim = gitclaim.GitClaim(
            repo=REPO, task="FR", id=f"#{num}", event="issues", action="opened", line="x"
        )
        gitclaim.apply_queue_event(tmp_path, claim)

    mock_post = _mock_post_dispatch()
    out = cd.tick(tmp_path, post=mock_post)

    # Should dispatch exactly 2 jobs
    assert out["dispatched"] == 2, f"Expected 2 dispatches, got {out['dispatched']}"
    # Should have 0 quota exhaustion
    assert out["quota"] == 0, f"Expected 0 quota exhaustion, got {out['quota']}"

    # Verify that copilot-jobs.json has exactly 2 jobs
    jobs = cd._load_jobs(tmp_path)
    job_count = len(jobs.get("jobs") or [])
    assert job_count == 2, f"Expected 2 jobs in copilot-jobs.json, got {job_count}"


def test_tick_no_third_dispatch_when_two_live(tmp_path):
    """Test that tick() does not start a 3rd task while 2 are live."""
    fi.handle_focus_cmd(tmp_path, f"high {REPO}")
    cd.set_allowance(tmp_path, remaining=10)
    
    now_f = time.time()

    # Pre-populate 2 live jobs by accepting them first
    for num in [10, 11]:
        claim = gitclaim.GitClaim(
            repo=REPO, task="FR", id=f"#{num}", event="issues", action="opened", line="x"
        )
        gitclaim.apply_queue_event(tmp_path, claim)
        # Accept the job to move it from unaccepted to accepted
        shop_listen.accept_job_by_ref(
            tmp_path, nick="copilot", channel="#bobiverse", repo=REPO, task="FR",
            ident=f"#{num}", title="test"
        )
        # Add to jobs file with current time (not 0)
        doc = cd._load_jobs(tmp_path)
        doc["jobs"].append({
            "repo": REPO, "task": "FR", "id": f"#{num}",
            "task_id": f"task-{num}", "started": now_f
        })
        cd._save_jobs(tmp_path, doc)

    # Create 3rd unaccepted high-priority row (should not be dispatched)
    claim = gitclaim.GitClaim(
        repo=REPO, task="FR", id=f"#12", event="issues", action="opened", line="x"
    )
    gitclaim.apply_queue_event(tmp_path, claim)

    mock_post = _mock_post_dispatch()
    out = cd.tick(tmp_path, post=mock_post, now=now_f)

    # Should not dispatch any new jobs (already 2 live)
    assert out["dispatched"] == 0, f"Expected 0 dispatches when 2 jobs live, got {out['dispatched']}"
    # Verify still exactly 2 jobs
    jobs = cd._load_jobs(tmp_path)
    job_count = len(jobs.get("jobs") or [])
    assert job_count == 2, f"Expected 2 jobs to remain, got {job_count}"


def test_tick_dispatches_second_when_first_completes(tmp_path):
    """Test that tick() dispatches another when slots become available."""
    fi.handle_focus_cmd(tmp_path, f"high {REPO}")
    cd.set_allowance(tmp_path, remaining=10)
    
    now_f = time.time()

    # Pre-populate 1 live job
    claim = gitclaim.GitClaim(
        repo=REPO, task="FR", id=f"#10", event="issues", action="opened", line="x"
    )
    gitclaim.apply_queue_event(tmp_path, claim)
    shop_listen.accept_job_by_ref(
        tmp_path, nick="copilot", channel="#bobiverse", repo=REPO, task="FR",
        ident=f"#10", title="test"
    )
    doc = cd._load_jobs(tmp_path)
    doc["jobs"].append({
        "repo": REPO, "task": "FR", "id": f"#10",
        "task_id": f"task-10", "started": now_f
    })
    cd._save_jobs(tmp_path, doc)

    # Create 3 more unaccepted high-priority rows
    for num in [11, 12, 13]:
        claim = gitclaim.GitClaim(
            repo=REPO, task="FR", id=f"#{num}", event="issues", action="opened", line="x"
        )
        gitclaim.apply_queue_event(tmp_path, claim)

    mock_post = _mock_post_dispatch()
    out = cd.tick(tmp_path, post=mock_post, now=now_f)

    # Should dispatch 1 more job to fill slot (now 2 live)
    assert out["dispatched"] == 1, f"Expected 1 dispatch to fill slot, got {out['dispatched']}"
    # Verify 2 jobs live
    jobs = cd._load_jobs(tmp_path)
    job_count = len(jobs.get("jobs") or [])
    assert job_count == 2, f"Expected 2 jobs after dispatch, got {job_count}"


def test_tick_multiple_calls_fills_slots(tmp_path):
    """Test that multiple tick() calls correctly fill and maintain 2 concurrent slots."""
    fi.handle_focus_cmd(tmp_path, f"high {REPO}")
    cd.set_allowance(tmp_path, remaining=50)

    # Create 5 high-priority rows
    for num in [10, 11, 12, 13, 14]:
        claim = gitclaim.GitClaim(
            repo=REPO, task="FR", id=f"#{num}", event="issues", action="opened", line="x"
        )
        gitclaim.apply_queue_event(tmp_path, claim)

    mock_post = _mock_post_dispatch()

    # First tick should dispatch 2
    out1 = cd.tick(tmp_path, post=mock_post)
    assert out1["dispatched"] == 2, f"First tick: expected 2 dispatches, got {out1['dispatched']}"

    # Reset mock_post for second tick
    mock_post = _mock_post_dispatch()
    # Second tick should dispatch 0 (already 2 live)
    out2 = cd.tick(tmp_path, post=mock_post)
    assert out2["dispatched"] == 0, f"Second tick: expected 0 dispatches (2 live), got {out2['dispatched']}"

    # Verify total 2 jobs live
    jobs = cd._load_jobs(tmp_path)
    job_count = len(jobs.get("jobs") or [])
    assert job_count == 2, f"Expected 2 jobs live, got {job_count}"


def test_tick_exhausted_flag_zero_when_dispatching(tmp_path):
    """Test that exhausted flag is not set when successfully dispatching."""
    fi.handle_focus_cmd(tmp_path, f"high {REPO}")
    cd.set_allowance(tmp_path, remaining=10)

    # Create 2 high-priority rows
    for num in [10, 11]:
        claim = gitclaim.GitClaim(
            repo=REPO, task="FR", id=f"#{num}", event="issues", action="opened", line="x"
        )
        gitclaim.apply_queue_event(tmp_path, claim)

    mock_post = _mock_post_dispatch()
    out = cd.tick(tmp_path, post=mock_post)

    # Should dispatch 2 jobs without exhaustion
    assert out["dispatched"] == 2, f"Expected 2 dispatches, got {out['dispatched']}"
    assert "exhausted" not in out, "Should not have exhausted flag when allowance remains"
    assert out.get("quota", 0) == 0, f"Should have 0 quota issues, got {out.get('quota', 0)}"

