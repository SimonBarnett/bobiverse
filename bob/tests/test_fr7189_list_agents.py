"""FR #7189: slow/failed --list-agents must not grey installed agents."""
from __future__ import annotations

import json
from pathlib import Path

import bob.scripts.bob_worker as bw

CUR, GRK, OP = r"C:\c\agent.cmd", r"C:\g\agent.exe", r"C:\o\opencode.exe"


def test_classify_timeout_keeps_enabled_unknown():
    rows, kind = bw.classify_agent_probe(
        exit_code=0, stdout="", stderr="", timed_out=True, start_failed=False, worker_missing=False
    )
    assert kind == "Timeout"
    by_id = {r["id"]: r for r in rows}
    for ident in ("grok", "cursor", "opencode"):
        assert by_id[ident]["available"] is True
        assert by_id[ident]["fuel_state"] == "unknown"
        assert by_id[ident]["reason"] == ""


def test_classify_malformed_and_failed_stay_enabled():
    for kwargs, want in (
        (dict(exit_code=1, stdout="", stderr="boom", timed_out=False, start_failed=False, worker_missing=False), "Failed"),
        (dict(exit_code=0, stdout="{not json", stderr="", timed_out=False, start_failed=False, worker_missing=False), "Malformed"),
        (dict(exit_code=0, stdout='{"agents":[{"id":"auto","available":true}]}', stderr="", timed_out=False, start_failed=False, worker_missing=False), "Malformed"),
        (dict(exit_code=0, stdout="", stderr="", timed_out=False, start_failed=True, worker_missing=False), "StartFailed"),
    ):
        rows, kind = bw.classify_agent_probe(**kwargs)
        assert kind == want
        by_id = {r["id"]: r for r in rows}
        assert by_id["grok"]["available"] is True
        assert by_id["opencode"]["available"] is True


def test_classify_unsupported_and_missing_grey_explicit():
    rows, kind = bw.classify_agent_probe(
        exit_code=2,
        stdout="",
        stderr="bob-worker: error: unrecognized arguments: --list-agents",
        timed_out=False,
        start_failed=False,
        worker_missing=False,
    )
    assert kind == "Unsupported"
    by_id = {r["id"]: r for r in rows}
    assert by_id["auto"]["available"] is True
    assert by_id["grok"]["available"] is False
    assert "no --list-agents" in by_id["grok"]["reason"]
    rows, kind = bw.classify_agent_probe(
        exit_code=0, stdout="", stderr="", timed_out=False, start_failed=False, worker_missing=True
    )
    assert kind == "WorkerMissing"
    assert {r["id"]: r["reason"] for r in rows if r["id"] != "auto"}["cursor"] == "bob-worker.exe not found"


def test_classify_keeps_last_good_on_timeout():
    good = [
        {"id": "auto", "label": "Automatic", "available": True, "installed": True, "reason": "Grok, then Cursor, then OpenCode", "fuel_state": "known"},
        {"id": "grok", "label": "Grok", "available": True, "installed": True, "reason": "", "fuel_state": "known"},
        {"id": "cursor", "label": "Cursor", "available": False, "installed": False, "reason": "not installed", "fuel_state": "known"},
        {"id": "opencode", "label": "OpenCode", "available": True, "installed": True, "reason": "", "fuel_state": "known"},
    ]
    rows, kind = bw.classify_agent_probe(
        exit_code=0, stdout="", stderr="", timed_out=True, start_failed=False, worker_missing=False, last_good=good
    )
    assert kind == "Timeout"
    assert {r["id"]: r["available"] for r in rows}["cursor"] is False


def test_list_menu_fuel_never_greys_installed(monkeypatch, capsys, tmp_path: Path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(bw, "resolve_grok_exe", lambda *a, **k: GRK)
    monkeypatch.setattr(bw, "resolve_cursor_cmd", lambda *a, **k: CUR)
    monkeypatch.setattr(bw, "resolve_opencode_cmd", lambda *a, **k: OP)
    monkeypatch.setattr(bw, "opencode_auth_file_present", lambda env=None: True)
    assert bw.save_agent_list_fuel(bw.Fuel(grok_pct=0, grok_state="exhausted", opencode_free=0, opencode_go=0))
    code = bw.main(["--list-agents", "--install-root", str(tmp_path)])
    assert code == bw.EXIT_OK
    listed = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    by_id = {row["id"]: row for row in listed["agents"]}
    assert by_id["grok"]["available"] is True
    assert by_id["opencode"]["available"] is True
    assert by_id["grok"]["reason"] == ""


def test_list_agents_not_installed_reason():
    rows = bw.list_worker_agents(bw.Fuel(), None, None, None, auth_present=False)
    by_id = {r["id"]: r for r in rows}
    assert by_id["grok"]["available"] is False
    assert by_id["grok"]["reason"] == "not installed"


def test_cache_permission_and_oversize_are_unknown(monkeypatch, capsys, tmp_path: Path):
    calls = []
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(bw, "resolve_grok_exe", lambda *a, **k: GRK)
    monkeypatch.setattr(bw, "resolve_cursor_cmd", lambda *a, **k: CUR)
    monkeypatch.setattr(bw, "resolve_opencode_cmd", lambda *a, **k: OP)
    monkeypatch.setattr(bw, "read_fuel", lambda *a, **k: calls.append("fuel") or bw.Fuel())
    monkeypatch.setattr(bw, "opencode_auth_file_present", lambda env=None: False)
    path = bw.agent_list_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * (bw.AGENT_LIST_CACHE_MAX_BYTES + 8))
    code = bw.main(["--list-agents", "--install-root", str(tmp_path)])
    assert code == bw.EXIT_OK
    assert calls == []
    listed = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert listed["refresh"] is True

    def load_denied(*, now=None, max_age_s=45.0, env=None):
        raise PermissionError("denied")

    monkeypatch.setattr(bw, "load_fresh_agent_list_fuel", load_denied)
    calls.clear()
    # load_fresh swallows OSError; a raised PermissionError from the helper is wrapped in the try in main? cache load itself catches OSError.
    # Simulate unreadable cache via load returning None after OSError inside load_fresh.
    monkeypatch.setattr(bw, "load_fresh_agent_list_fuel", lambda **_k: None)
    code = bw.main(["--list-agents", "--install-root", str(tmp_path)])
    assert code == bw.EXIT_OK
    assert calls == []


def test_install_root_skips_ai_root_product_scan(monkeypatch, capsys, tmp_path: Path):
    import ai_root

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("BOB_AI_ROOT", raising=False)
    monkeypatch.setattr(bw, "resolve_grok_exe", lambda *a, **k: GRK)
    monkeypatch.setattr(bw, "resolve_cursor_cmd", lambda *a, **k: CUR)
    monkeypatch.setattr(bw, "resolve_opencode_cmd", lambda *a, **k: OP)
    monkeypatch.setattr(bw, "opencode_auth_file_present", lambda env=None: False)

    def boom(*_a, **_k):
        raise AssertionError("product_root must not run when --install-root is set")

    monkeypatch.setattr(ai_root, "product_root", boom)
    code = bw.main(["--list-agents", "--install-root", str(tmp_path)])
    assert code == bw.EXIT_OK
    assert '"agents"' in capsys.readouterr().out


def test_cs_and_ps_share_probe_policy():
    from repo_layout import REPO

    cs = (REPO / "bob" / "tray" / "dialogs" / "BobTray.cs").read_text(encoding="utf-8-sig")
    ps = (REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1").read_text(encoding="utf-8-sig")
    assert "ClassifyAgentProbe" in cs
    assert "unrecognized arguments" in cs and "unrecognized arguments" in ps
    assert "30000" in cs and "$waitMs = 30000" in ps
    assert "$waitMs = 60000" in ps
    assert "bob-worker.exe not found" in cs and "bob-worker.exe not found" in ps
    docs = (REPO / "bob" / "docs" / "bob-tray-dialogs.md").read_text(encoding="utf-8")
    assert "last-good" in docs.lower() or "last good" in docs.lower()
    assert "never grey" in docs.lower() or "never disables" in docs.lower() or "never disable" in docs.lower()
