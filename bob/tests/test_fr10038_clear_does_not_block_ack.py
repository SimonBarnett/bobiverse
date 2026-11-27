"""FR #10038: OpenCode Clear runs off the seat thread so ACK is not starved."""
from repo_layout import ROOT

SRC = (ROOT / "bob" / "scripts" / "bob_worker.py").read_text(encoding="utf-8")


def test_fr10038_clear_is_a_daemon_thread():
    fn = SRC.index("def _opencode_job_end_cleanup")
    body = SRC[fn:fn + 1400]
    assert "FR #10038" in body
    assert 'name="oc-clear"' in body
    assert "daemon=True" in body
    assert body.index("Thread(") < body.index("_clear_per_job_seat_state")
