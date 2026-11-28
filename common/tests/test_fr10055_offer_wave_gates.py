"""FR #10055 / #10057 / #10059 offer gates."""
import digest_offer_gate as gate


def test_fr10055_finished_fix_is_not_reoffered():
    row = {
        "task": "FIX",
        "repo": "SimonBarnett/bobiverse",
        "id": "9417",
        "recent_done_keys": ["SimonBarnett/bobiverse#9417"],
    }
    assert gate.finished_fix_reoffer_reason(row) == "finished-fix"
    assert gate.finished_fix_reoffer_reason({"task": "FIX", "repo": "SimonBarnett/bobiverse", "id": "1"}) is None


def test_fr10057_row_outside_wave_is_blocked():
    row = {"id": "9803", "operator_wave_open": ["9763", "9764", "9766"]}
    assert gate.outside_operator_wave_reason(row) == "outside-operator-wave"
    assert gate.outside_operator_wave_reason({"id": "9763", "operator_wave_open": ["9763"]}) is None


def test_fr10055_queue_done_and_wave_feed_the_gate():
    import gitclaim

    repo = "SimonBarnett/bobiverse"
    fix = {"task": "FIX", "repo": repo, "id": "9417", "state": "open"}
    doc = {
        "done": [{"task": "FIX", "repo": repo, "id": "#9417"}],
        "operator_wave_open": ["9763"],
        "unaccepted": [],
        "accepted": [],
    }
    assert gitclaim.depends_gate_reason(fix, doc) == "finished-fix"
    other = {"task": "FR", "repo": repo, "id": "9803", "state": "open", "body": "Depends-on: (none)\n"}
    assert gitclaim.depends_gate_reason(other, doc) == "outside-operator-wave"


def test_fr10059_open_depend_blocks():
    assert gate.open_depend_blocks("open", ["hold"]) is True
    assert gate.open_depend_blocks("open", []) is True
    assert gate.open_depend_blocks("closed", ["hold"]) is False
