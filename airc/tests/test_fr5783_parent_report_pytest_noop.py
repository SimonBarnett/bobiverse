"""FR #5783: parent_report / report_verb_failure must not post under pytest."""
from __future__ import annotations

import airc_fail_intake as fi
import airc_isolated as iso


def test_fr5783_intake_allowed_false_under_pytest(monkeypatch):
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_fr5783_intake_allowed_false_under_pytest")
    assert fi.intake_allowed() is False


def test_fr5783_report_verb_failure_skips_without_filer(monkeypatch):
    posts: list[dict] = []

    def boom_post(*_a, **_k):
        posts.append({"hit": True})
        raise AssertionError("must not call _native_post under pytest")

    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_fr5783_report_verb_failure_skips")
    monkeypatch.setattr(fi, "_native_post", boom_post)
    out = fi.report_verb_failure(
        "legion",
        "worker_died",
        args={"detail": "empty-stdout"},
        version="1.0.7",
        machine="flamingo",
        wait_s=0,
    )
    assert out.get("skipped") == "pytest-or-policy"
    assert out.get("ok") is False
    assert posts == []


def test_fr5783_worker_died_path_does_not_post_intake(monkeypatch):
    """Acceptance: call_isolated_module worker_died under pytest never hits _post_intake."""
    posts: list[dict] = []

    def boom_post(*_a, **_k):
        posts.append({"hit": True})
        raise AssertionError("_post_intake must not run under pytest worker_died")

    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_fr5783_worker_died_path")
    monkeypatch.setattr(fi, "_native_post", boom_post)
    try:
        import crash_report

        monkeypatch.setattr(crash_report, "_post_intake", boom_post)
    except Exception:
        pass

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
    assert posts == []


def test_fr5783_filer_post_still_runs_under_pytest():
    """Injected filer_post remains the unit-test escape hatch."""
    posts: list[dict] = []

    def fake(title, body, *, repo, sig, exe):
        posts.append({"sig": sig})
        return {"ok": True}

    out = fi.report_verb_failure(
        "extension",
        RuntimeError("inject"),
        version="1.0.7",
        machine="walrus",
        wait_s=0,
        filer_post=fake,
    )
    assert out.get("ok") is True
    assert posts
    assert "skipped" not in out
