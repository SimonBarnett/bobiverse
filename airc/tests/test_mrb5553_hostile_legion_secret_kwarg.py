"""MRB #5553 hostile pins: LEGION secret= kwarg, never process environ (FR #5529)."""
from __future__ import annotations

import os

import airc_legion as lg
from repo_layout import ROOT


def test_mrb5553_modern_runner_receives_secret_kwarg(monkeypatch):
    monkeypatch.setattr(
        lg,
        "read_remote_airc_profile_result",
        lambda host, **_k: {"profile": "", "ok": True, "found": False, "detail": "not-found"},
    )
    secret = "FAKE_" + "secret_kwarg_only"
    seen: dict = {}

    def run_fn(spec: dict, *, secret: str = "") -> dict:
        seen["secret"] = secret
        seen["env"] = os.environ.get("AIRC_LEGION_PASSWORD")
        return {"ok": True, "status": "dry-run"}

    prev = os.environ.pop("AIRC_LEGION_PASSWORD", None)
    try:
        body = lg.installer_legion_work(
            "walrus",
            whatif=True,
            run_fn=run_fn,
            credman=lambda: {"username": "wonderland\\legion", "password": secret},
        )
        assert body["ok"] is True
        assert seen["secret"] == secret
        assert seen["env"] is None
        assert os.environ.get("AIRC_LEGION_PASSWORD") is None
        assert secret not in str(body)
    finally:
        if prev is None:
            os.environ.pop("AIRC_LEGION_PASSWORD", None)
        else:
            os.environ["AIRC_LEGION_PASSWORD"] = prev


def test_mrb5553_source_pins_secret_kwarg_not_environ_assign():
    src = (ROOT / "airc" / "scripts" / "airc_legion.py").read_text(encoding="utf-8")
    assert "runner(spec, secret=secret)" in src
    assert 'os.environ["AIRC_LEGION_PASSWORD"]' not in src
    assert "os.environ['AIRC_LEGION_PASSWORD']" not in src
    assert "FR #5529" in src
    assert not (ROOT / "airc" / "scripts" / "airc_legion.py").read_bytes().startswith(
        b"\xef\xbb\xbf"
    )
