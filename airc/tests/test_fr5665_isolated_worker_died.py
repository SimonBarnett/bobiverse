"""FR #5665: killed/missing isolated worker must not look like empty success."""
from __future__ import annotations

import airc_extension as ex
import airc_isolated as iso
import airc_legion as lg
import airc_network as nw


def test_fr5665_call_isolated_nonzero_is_worker_died():
    class P:
        returncode = 1
        stdout = ""
        stderr = ""

    out = iso.call_isolated_module(
        "airc_extension",
        "fill_holes_work",
        {},
        runner=lambda *_a, **_k: P(),
    )
    assert out["ok"] is False
    assert out["error"] == "worker_died"
    assert out.get("detail")


def test_fr5665_call_isolated_empty_stdout_zero_is_worker_died():
    class P:
        returncode = 0
        stdout = "   "
        stderr = ""

    out = iso.call_isolated_module(
        "airc_network",
        "inventory_work",
        {},
        runner=lambda *_a, **_k: P(),
    )
    assert out["ok"] is False
    assert out["error"] == "worker_died"


def test_fr5665_call_isolated_bad_json_nonzero_is_worker_died():
    class P:
        returncode = 1
        stdout = "{not-json"
        stderr = "killed"

    out = iso.call_isolated_module(
        "airc_legion",
        "installer_legion_work",
        {},
        runner=lambda *_a, **_k: P(),
    )
    assert out["ok"] is False
    assert out["error"] == "worker_died"


def test_fr5665_is_worker_fault_helper():
    assert iso.is_worker_fault({"ok": False, "error": "worker_died"})
    assert iso.is_worker_fault({"ok": False, "error": "isolated-fault:exit-1"})
    assert not iso.is_worker_fault({"ok": True, "hosts": []})
    assert not iso.is_worker_fault({"ok": False, "error": "credman-missing", "hosts": []})


def test_fr5665_extension_log_from_worker_died_not_empty_success():
    log = ex.extension_log_from_payload(
        "install",
        whatif=True,
        payload={"ok": False, "error": "worker_died", "detail": "exit-1"},
    )
    assert log["failure_count"] >= 1
    assert any(
        f.get("error") == "worker_died" and f.get("step") == "worker"
        for f in (log.get("failures") or [])
    )
    assert (log.get("gpo") or {}).get("reason") == "worker_died"
    # Must not look like fill-holes-only empty success (FR repro).
    assert (log.get("gpo") or {}).get("reason") != "gpo_step_skipped"
    delivered = ex.deliver_extension_log(job_id="e4000001", log=log, offer=None)
    assert "exit=0" not in delivered["done"]
    assert "exit=1" in delivered["done"]


def test_fr5665_extension_log_legacy_isolated_fault_prefix():
    log = ex.extension_log_from_payload(
        "install",
        whatif=True,
        payload={"ok": False, "error": "isolated-fault:exit-1"},
    )
    assert log["failure_count"] >= 1
    assert any(f.get("error") == "worker_died" for f in log["failures"])


def test_fr5665_network_from_child_fault_has_failures(monkeypatch):
    seen: list = []

    def fake_call(module, func, kwargs, **_k):
        return {"ok": False, "error": "worker_died", "detail": "exit-1"}

    monkeypatch.setattr(iso, "call_isolated_module", fake_call)
    monkeypatch.setattr("airc_isolated.call_isolated_module", fake_call)

    def on_done(res):
        seen.append(res)

    nw.run_network_verb(
        action="diag",
        whatif=True,
        job_id="n1000001",
        wait=False,
        on_done=on_done,
    )
    # Background thread may need a tick
    import time

    for _ in range(50):
        if seen:
            break
        time.sleep(0.02)
    assert seen, "on_done never fired"
    res = seen[0]
    assert res.ok is False
    assert res.failures
    assert any(
        (f.get("error") == "worker_died" if isinstance(f, dict) else False)
        for f in res.failures
    )
    payload = nw.build_network_payload(
        "diag", whatif=True, hosts=list(res.hosts or []), failures=list(res.failures or [])
    )
    assert payload["failure_count"] >= 1
    delivered = nw.deliver_network_payload(
        job_id="n1000001", payload=payload, offer=None
    )
    assert "exit=1" in delivered["done"]


def test_fr5665_legion_worker_died_exit_nonzero(monkeypatch):
    seen: list = []

    def fake_call(module, func, kwargs, **_k):
        return {"ok": False, "error": "worker_died", "detail": "exit-1"}

    monkeypatch.setattr(iso, "call_isolated_module", fake_call)
    monkeypatch.setattr("airc_isolated.call_isolated_module", fake_call)

    def on_done(res):
        seen.append(res)

    lg.run_legion_verb(
        target="flamingo",
        whatif=True,
        job_id="b1000001",
        wait=False,
        on_done=on_done,
    )
    import time

    for _ in range(50):
        if seen:
            break
        time.sleep(0.02)
    assert seen
    res = seen[0]
    assert res.failures
    assert any(f.get("error") == "worker_died" for f in res.failures)
    log = lg.build_legion_log(
        target="flamingo",
        whatif=True,
        summary=res.status or "failed",
        failures=list(res.failures or []),
    )
    delivered = lg.deliver_legion_log(job_id="b1000001", log=log, offer=None)
    assert "exit=1" in delivered["done"]


def test_fr5665_skills_document_worker_died():
    from repo_layout import ROOT

    blob = (
        (ROOT / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md").read_text(
            encoding="utf-8"
        )
        + (ROOT / "airc/.grok/skills/bobiverse-airc-commands/SKILL.md").read_text(
            encoding="utf-8"
        )
    )
    assert "5665" in blob
    assert "worker_died" in blob
