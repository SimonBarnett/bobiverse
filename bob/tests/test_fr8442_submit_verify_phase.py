"""FR #8442: submit-verify publishes progress_phase and clears it."""

from __future__ import annotations

import bob.scripts.bob_worker as bw


def test_fr8442_submit_verify_sets_then_clears_phase(monkeypatch):
    phases = []

    def _post(**kwargs):
        phases.append(kwargs.get("progress_phase"))
        return True

    monkeypatch.setenv("BOB_NICK", "flamingo-22532")
    monkeypatch.setenv("BOB_MACHINE", "flamingo")
    monkeypatch.setattr(bw, "post_digest_progress_heartbeat", _post)
    ok = bw.inject_with_submit_verify(
        1,
        "assign",
        inject_fn=lambda *_a, **_k: True,
        probe_fn=lambda: True,
        sleep=lambda _s: None,
        clock=lambda: 0.0,
        verify_s=0.0,
        max_retries=0,
        backoffs=(),
    )
    assert ok is True
    assert phases[0] == "submit-verify"
    assert phases[-1] == ""
    assert bw.submit_verify_in_flight() is False


def test_fr8442_empty_phase_clears_doing_row(tmp_path, monkeypatch):
    import bobreport
    import registered_machines

    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["online"] = True
    digest["machines"]["flamingo"]["worker_list"] = [{
        "nick": "flamingo-22532",
        "state": "doing",
        "work": "working",
        "progress_phase": "submit-verify",
    }]
    bobreport.save_digest(tmp_path, digest)
    out = bobreport._apply_worker_op(
        tmp_path,
        "worker-work",
        "flamingo",
        {
            "nick": "flamingo-22532",
            "state": "doing",
            "progress_phase": "",
            "last_progress": "2026-11-20T13:00:00Z",
        },
    )
    assert out.ok is True
    loaded = bobreport.load_digest(tmp_path)
    row = loaded["machines"]["flamingo"]["worker_list"][0]
    assert "progress_phase" not in row
