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
