"""FR #10049: Plan, Jeeves, and Priority do not count toward the worker cap."""
import worker_irc_seats as seats


def test_fr10049_priority_and_jeeves_are_not_agent_roots():
    procs = [
        (10, 1, "bob-worker.exe", "--mode agent --agent grok"),
        (11, 1, "bob-worker.exe", "--mode agent --agent priority"),
        (12, 1, "bob-worker.exe", "--mode agent --agent jeeves"),
        (13, 1, "bob-worker.exe", "--mode plan"),
    ]
    roots = seats.live_agent_root_pids(procs)
    assert roots == {10}


def test_fr10049_marker_kind_priority_is_omitted(tmp_path, monkeypatch):
    d = tmp_path / "seats"
    d.mkdir()
    monkeypatch.setattr(seats, "seats_dir", lambda root=None: d)
    (d / "a.irc.json").write_text(
        '{"mode":"agent","agent":"priority","pid":42,"machine":"redqueen"}',
        encoding="utf-8",
    )
    (d / "b.irc.json").write_text(
        '{"mode":"agent","agent":"grok","pid":43,"machine":"redqueen"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(seats, "pid_alive", lambda pid: True)
    live = seats.list_live_irc_agent_seats(pid_alive_fn=lambda pid: True)
    kinds = {str(row.get("agent")) for row in live}
    assert kinds == {"grok"}
