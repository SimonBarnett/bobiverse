"""FR #5529: LEGION must not put CredMan secret in process-wide os.environ."""
from __future__ import annotations

import os

import airc_legion as lg


def test_fr5529_installer_does_not_set_process_env():
    secret = "FAKE_" + "no_global_env"
    seen: list[str | None] = []

    def run_fn(spec: dict) -> dict:
        seen.append(os.environ.get("AIRC_LEGION_PASSWORD"))
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
        assert seen == [None]
        assert os.environ.get("AIRC_LEGION_PASSWORD") is None
    finally:
        if prev is None:
            os.environ.pop("AIRC_LEGION_PASSWORD", None)
        else:
            os.environ["AIRC_LEGION_PASSWORD"] = prev


def test_fr5529_source_does_not_assign_global_env():
    src = open(lg.__file__, encoding="utf-8").read()
    assert 'os.environ["AIRC_LEGION_PASSWORD"]' not in src
    assert "os.environ['AIRC_LEGION_PASSWORD']" not in src
    assert "FR #5529" in src
