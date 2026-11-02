"""FR #5905: pack Node SDK + run-repprep mjs into priority-worker resolver paths."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import airc_console as ac
from repo_layout import ROOT

PW = ROOT / "airc" / "priority-worker"
MJS = PW / "sdk" / "run-repprep-via-exec.mjs"
PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
PKG = PW / "package.json"


def test_fr5905_layout_ships_mjs_and_package_dep():
    assert MJS.is_file(), "sdk/run-repprep-via-exec.mjs must ship in the repo"
    raw = MJS.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = MJS.read_text(encoding="utf-8")
    assert "PRIORITY_SDK_PASSWORD" in text
    assert "priority-web-sdk" in text
    assert "--name" in text
    pkg = json.loads(PKG.read_text(encoding="utf-8"))
    deps = pkg.get("dependencies") or {}
    assert "priority-web-sdk" in deps
    readme = (PW / "README.md").read_text(encoding="utf-8")
    assert "FR #5905" in readme or "5905" in readme
    assert "node" in readme.lower()
    assert "drop" in readme.lower()


def test_fr5905_resolver_finds_sdk_mjs(tmp_path, monkeypatch):
    """_priority_sdk_repprep must resolve packed sdk/run-repprep-via-exec.mjs."""
    root = tmp_path / "airc-install"
    pw = root / "airc" / "priority-worker" / "sdk"
    pw.mkdir(parents=True)
    mjs = pw / "run-repprep-via-exec.mjs"
    mjs.write_text("// stub\n", encoding="utf-8")
    monkeypatch.setenv("AIRC_INSTALL_ROOT", str(root))
    monkeypatch.setattr(
        ac._priority,
        "resolve_priority_worker_dir",
        lambda _r: root / "airc" / "priority-worker",
    )
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"] = list(argv)
        seen["env_has_pw"] = bool((kw.get("env") or {}).get("PRIORITY_SDK_PASSWORD"))
        class P:
            returncode = 0
            stdout = '{"ok":true,"ended":true,"errors":[]}\n'
            stderr = ""
        return P()

    out = ac._priority_sdk_repprep(
        ename="CUSTOMERS",
        instance={
            "credentialTarget": "PriorityWeb/x",
            "company": "c",
            "url": "https://example.invalid",
            "user": "u",
        },
        cred_fetcher=lambda _t: "FAKE_priority_pw",
        node_runner=fake_run,
    )
    assert out.get("ok") is True
    assert seen["argv"][1].replace("\\", "/").endswith(
        "priority-worker/sdk/run-repprep-via-exec.mjs"
    )
    assert seen["env_has_pw"] is True
    # Password must not appear in returned payload.
    blob = json.dumps(out).lower()
    assert "fake_priority" not in blob
    assert "password=" not in blob


def test_fr5905_node_missing_reason(monkeypatch, tmp_path):
    root = tmp_path / "airc-install"
    pw = root / "airc" / "priority-worker" / "sdk"
    pw.mkdir(parents=True)
    (pw / "run-repprep-via-exec.mjs").write_text("// stub\n", encoding="utf-8")
    monkeypatch.setenv("AIRC_INSTALL_ROOT", str(root))
    monkeypatch.setenv("AIRC_PRIORITY_NODE", str(tmp_path / "no-such-node.exe"))
    monkeypatch.delenv("NODE_EXE", raising=False)
    monkeypatch.setattr(
        ac._priority,
        "resolve_priority_worker_dir",
        lambda _r: root / "airc" / "priority-worker",
    )
    out = ac._priority_sdk_repprep(
        ename="CUSTOMERS",
        instance={
            "credentialTarget": "t",
            "company": "c",
            "url": "https://example.invalid",
            "user": "u",
        },
        cred_fetcher=lambda _t: "FAKE_pw",
    )
    assert out.get("ok") is False
    assert out.get("reason") == "node_missing"


def test_fr5905_pack_script_requires_mjs_and_npm_ci():
    pack = PACK.read_text(encoding="utf-8")
    assert "FR #5905" in pack
    assert "run-repprep-via-exec.mjs" in pack
    assert "npm ci" in pack
    assert "node_modules\\priority-web-sdk" in pack or "node_modules/priority-web-sdk" in pack


def test_fr5905_mjs_cli_emits_json_when_name_missing():
    """Wrapper emits JSON for missing --name without printing secrets."""
    import shutil

    node = os.environ.get("AIRC_PRIORITY_NODE") or os.environ.get("NODE_EXE") or "node"
    node_path = node if os.path.isfile(node) else shutil.which(node)
    if not node_path:
        return
    env = dict(os.environ)
    env["PRIORITY_SDK_PASSWORD"] = "FAKE_pw"
    proc = subprocess.run(
        [node_path, str(MJS), "--company", "c", "--url", "https://example.invalid", "--user", "u"],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        cwd=str(PW),
    )
    lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    assert lines, proc.stderr
    payload = json.loads(lines[-1])
    assert payload.get("ok") is False
    assert "name_missing" in (payload.get("errors") or [])
    blob = (proc.stdout or "") + (proc.stderr or "")
    assert "FAKE_pw" not in blob
