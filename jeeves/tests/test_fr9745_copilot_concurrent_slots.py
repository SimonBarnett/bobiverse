"""FR #9745: Copilot concurrent slots (max 2 live tasks)."""
from __future__ import annotations

import copilot_dispatch as cd
import focus_ignore as fi
import gitclaim


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


def test_max_concurrent_copilot_constant():
    """Verify MAX_CONCURRENT_COPILOT constant is set to 2."""
    assert cd.MAX_CONCURRENT_COPILOT == 2


def test_tick_dispatches_up_to_max_concurrent(tmp_path):
    """Verify tick dispatches up to MAX_CONCURRENT_COPILOT tasks."""
    fi.handle_focus_cmd(tmp_path, f"high {REPO}")
    cd.set_allowance(tmp_path, remaining=50)
    
    # Add multiple high-priority rows to the queue.
    for num in range(100, 103):
        claim = gitclaim.GitClaim(
            repo=REPO,
            task="FR",
            id=f"#{num}",
            event="issues",
            action="opened",
            line="x",
        )
        gitclaim.apply_queue_event(tmp_path, claim)
    
    # Track dispatches
    dispatches = []
    task_id_counter = [1]
    
    def mock_post(url, body):
        dispatches.append(body)
        # Return success (200 OK means accepted by GitHub) with task_id
        task_id_counter[0] += 1
        return {"status": 200, "task_id": f"task-{task_id_counter[0]}"}
    
    # First tick: should dispatch 1 task (slot 1/2 filled)
    out1 = cd.tick(tmp_path, post=mock_post)
    assert out1["dispatched"] == 1, f"Expected 1 dispatch, got {out1}"
    assert len(dispatches) == 1
    
    # Second tick: should dispatch 1 more task (slot 2/2 filled)
    out2 = cd.tick(tmp_path, post=mock_post)
    assert out2["dispatched"] == 1, f"Expected 1 dispatch, got {out2}"
    assert len(dispatches) == 2
    
    # Third tick: should NOT dispatch (slots are full)
    out3 = cd.tick(tmp_path, post=mock_post)
    assert out3["dispatched"] == 0, f"Expected 0 dispatches (slots full), got {out3}"
    assert len(dispatches) == 2


def test_tick_stops_at_max_concurrent_no_third(tmp_path):
    """Verify tick never starts a 3rd task while 2 are live."""
    fi.handle_focus_cmd(tmp_path, f"high {REPO}")
    cd.set_allowance(tmp_path, remaining=50)
    
    # Add many high-priority rows to ensure we have candidates.
    for num in range(100, 110):
        claim = gitclaim.GitClaim(
            repo=REPO,
            task="FR",
            id=f"#{num}",
            event="issues",
            action="opened",
            line="x",
        )
        gitclaim.apply_queue_event(tmp_path, claim)
    
    dispatches = []
    task_id_counter = [1]
    
    def mock_post(url, body):
        dispatches.append(body)
        task_id_counter[0] += 1
        return {"status": 200, "task_id": f"task-{task_id_counter[0]}"}
    
    # Dispatch up to 2 tasks.
    cd.tick(tmp_path, post=mock_post)
    cd.tick(tmp_path, post=mock_post)
    
    assert len(dispatches) == 2
    
    # Many more ticks should not dispatch a 3rd task.
    for _ in range(5):
        out = cd.tick(tmp_path, post=mock_post)
        assert out["dispatched"] == 0
    
    assert len(dispatches) == 2, "Should never dispatch a 3rd task"


def test_tick_resumes_dispatch_after_slot_freed(tmp_path):
    """Verify tick resumes dispatch when a slot becomes free."""
    fi.handle_focus_cmd(tmp_path, f"high {REPO}")
    cd.set_allowance(tmp_path, remaining=50)
    
    # Add multiple rows.
    for num in range(100, 105):
        claim = gitclaim.GitClaim(
            repo=REPO,
            task="FR",
            id=f"#{num}",
            event="issues",
            action="opened",
            line="x",
        )
        gitclaim.apply_queue_event(tmp_path, claim)
    
    dispatches = []
    task_id_counter = [1]
    
    def mock_post(url, body):
        dispatches.append(body)
        task_id_counter[0] += 1
        return {"status": 200, "task_id": f"task-{task_id_counter[0]}"}
    
    # Dispatch 2 tasks
    cd.tick(tmp_path, post=mock_post)
    cd.tick(tmp_path, post=mock_post)
    assert len(dispatches) == 2
    
    # Manually remove one job from the jobs list to simulate it completing.
    jobs_doc = cd._load_jobs(tmp_path)
    if jobs_doc.get("jobs"):
        jobs_doc["jobs"].pop(0)
        cd._save_jobs(tmp_path, jobs_doc)
    
    # Now tick should dispatch again (filling the freed slot).
    out = cd.tick(tmp_path, post=mock_post)
    assert out["dispatched"] == 1
    assert len(dispatches) == 3


def test_tick_exhausted_does_not_exceed_max(tmp_path):
    """Verify exhausted allowance doesn't exceed max concurrent."""
    fi.handle_focus_cmd(tmp_path, f"high {REPO}")
    
    # Set exhausted allowance
    cd.set_allowance(tmp_path, remaining=0, exhausted=True)
    
    # Add rows (even though allowance is exhausted)
    for num in range(100, 103):
        claim = gitclaim.GitClaim(
            repo=REPO,
            task="FR",
            id=f"#{num}",
            event="issues",
            action="opened",
            line="x",
        )
        gitclaim.apply_queue_event(tmp_path, claim)
    
    dispatches = []
    
    def mock_post(url, body):
        dispatches.append(body)
        return {"status": 200, "task_id": "task-1"}
    
    # Tick should not dispatch due to exhausted allowance
    out = cd.tick(tmp_path, post=mock_post)
    assert out.get("disabled") or not out.get("dispatched")
    assert len(dispatches) == 0


