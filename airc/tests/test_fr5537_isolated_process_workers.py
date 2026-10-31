"""FR #5537: NETWORK/EXTENSION/LEGION default work runs in a child process."""
from __future__ import annotations

import io
import json
import os

import airc_extension as ex
import airc_isolated as iso
import airc_legion as lg
import airc_network as nw
from repo_layout import ROOT


def test_fr5537_packaged_fn_detect():
    assert iso.is_packaged_work(lg.installer_legion_work)
    assert iso.is_packaged_work(nw.inventory_work)
    assert iso.is_packaged_work(ex.fill_holes_work)
    assert not iso.is_packaged_work(lambda **k: {})
    assert not iso.is_packaged_work(None)


def test_fr5537_child_job_main_inventory(monkeypatch):
    monkeypatch.setattr(
        "airc_network.inventory_work",
        lambda **k: {"ok": True, "hosts": [{"hostname": "box1"}], "pid": os.getpid()},
    )
    spec = json.dumps(
        {"module": "airc_network", "func": "inventory_work", "kwargs": {"action": "diag"}}
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(spec))
    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)
    rc = iso.isolated_job_main()
    assert rc == 0
    data = json.loads(buf.getvalue())
    assert data["ok"] is True
    assert data["hosts"][0]["hostname"] == "box1"


def test_fr5537_refuses_foreign_module():
    spec = json.dumps({"module": "os", "func": "getcwd", "kwargs": {}})
    import io as _io

    import airc_isolated as m

    monkeypatch_stdin = _io.StringIO(spec)
    # call with patched stdin via isolated_job_main reading sys.stdin
    import sys

    old = sys.stdin
    sys.stdin = monkeypatch_stdin
    old_out = sys.stdout
    sys.stdout = _io.StringIO()
    try:
        rc = m.isolated_job_main()
        out = sys.stdout.getvalue()
    finally:
        sys.stdin = old
        sys.stdout = old_out
    assert rc == 2
    assert "refused-target" in out


def test_fr5537_call_isolated_uses_child_argv():
    seen: dict = {}

    def runner(argv, **kwargs):
        seen["argv"] = list(argv)
        seen["input"] = kwargs.get("input")
        seen["env"] = kwargs.get("env") or {}

        class P:
            returncode = 0
            stdout = '{"ok":true,"hosts":[]}'
            stderr = ""

        return P()

    data = iso.call_isolated_module(
        "airc_network",
        "inventory_work",
        {"action": "diag", "password": "FAKE_SHOULD_STRIP"},
        runner=runner,
    )
    assert data == {"ok": True, "hosts": []}
    assert "airc_isolated.py" in seen["argv"][-1] or "--isolated-job" in seen["argv"]
    assert "FAKE_SHOULD_STRIP" not in (seen["input"] or "")
    assert "AIRC_LEGION_PASSWORD" not in seen["env"]


def test_fr5537_default_legion_async_uses_isolated_helper(monkeypatch):
    seen: list[tuple] = []

    def fake(module, func, kwargs, **_k):
        seen.append((module, func, kwargs))
        return {"ok": True, "status": "dry-run", "target": kwargs.get("target")}

    monkeypatch.setattr(iso, "call_isolated_module", fake)
    monkeypatch.setattr("airc_isolated.call_isolated_module", fake)
    res = lg.run_legion_verb(target="walrus", whatif=True, wait=False, job_id="aabbccdd")
    assert "LEGION accepted" in res.reply
    # packaged path scheduled; allow the join thread a moment
    import time

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not seen:
        time.sleep(0.02)
    assert seen
    assert seen[0][0] == "airc_legion"
    assert seen[0][1] == "installer_legion_work"
    assert "password" not in json.dumps(seen[0][2])


def test_fr5537_injected_worker_not_forced_through_subprocess():
    called = {"n": 0}

    def worker(target, **_k):
        called["n"] += 1
        return {"ok": True, "status": "dry-run"}

    res = lg.run_legion_verb(
        target="walrus", worker=worker, wait=True, job_id="11223344"
    )
    assert called["n"] == 1
    assert res.status == "dry-run"


def test_fr5537_source_and_pack_pins():
    for rel in (
        "airc/scripts/airc_legion.py",
        "airc/scripts/airc_network.py",
        "airc/scripts/airc_extension.py",
        "airc/scripts/airc_console_service.py",
        "airc/scripts/Build-Airc.ps1",
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "airc_isolated" in text or "isolated-job" in text
    assert (ROOT / "airc" / "scripts" / "airc_isolated.py").is_file()
    assert not (ROOT / "airc" / "scripts" / "airc_isolated.py").read_bytes().startswith(
        b"\xef\xbb\xbf"
    )
    pack = (ROOT / "airc" / "scripts" / "Pack-AircConsoleRelease.ps1").read_text(
        encoding="utf-8"
    )
    assert "airc_isolated.py" in pack
