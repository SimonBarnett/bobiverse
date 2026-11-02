"""FR #5905: pack Node SDK + run-repprep mjs into priority-worker resolver paths."""
from __future__ import annotations

import json
import pytest
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import airc_console as ac
from repo_layout import ROOT

PW = ROOT / "airc" / "priority-worker"
MJS = PW / "sdk" / "run-repprep-via-exec.mjs"
FORM_MJS = PW / "sdk" / "run-formprep-via-eform.mjs"
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
    assert "name_field_missing" in text  # FR #5927
    assert FORM_MJS.is_file(), "sdk/run-formprep-via-eform.mjs must ship (FR #5946)"
    form_raw = FORM_MJS.read_bytes()
    assert not form_raw.startswith(b"\xef\xbb\xbf")
    form_text = FORM_MJS.read_text(encoding="utf-8")
    assert "PRIORITY_SDK_PASSWORD" in form_text
    assert "FORMPREPDRCT2" in form_text
    pkg = json.loads(PKG.read_text(encoding="utf-8"))
    deps = pkg.get("dependencies") or {}
    assert "priority-web-sdk" in deps
    readme = (PW / "README.md").read_text(encoding="utf-8")
    assert "FR #5905" in readme or "5905" in readme
    assert "run-formprep-via-eform.mjs" in readme
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
        cred_fetcher=lambda _t: "secret-placeholder-priority-pw",
        node_runner=fake_run,
    )
    assert out.get("ok") is True
    assert seen["argv"][1].replace("\\", "/").endswith(
        "priority-worker/sdk/run-repprep-via-exec.mjs"
    )
    assert seen["env_has_pw"] is True
    # Password must not appear in returned payload.
    blob = json.dumps(out).lower()
    assert "secret-placeholder-priority" not in blob
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
        cred_fetcher=lambda _t: "secret-placeholder-pw",
    )
    assert out.get("ok") is False
    assert out.get("reason") == "node_missing"


def test_fr5905_pack_script_requires_mjs_and_npm_ci():
    pack = PACK.read_text(encoding="utf-8")
    assert "FR #5905" in pack
    assert "run-repprep-via-exec.mjs" in pack
    assert "run-formprep-via-eform.mjs" in pack  # FR #5946
    assert "npm ci" in pack
    assert "node_modules\\priority-web-sdk" in pack or "node_modules/priority-web-sdk" in pack


def test_fr5946_resolver_finds_formprep_mjs(tmp_path, monkeypatch):
    """FR #6003: default form prepare uses repprep mjs; eform only when opted in."""
    root = tmp_path / "airc-install"
    pw = root / "airc" / "priority-worker" / "sdk"
    pw.mkdir(parents=True)
    (pw / "run-repprep-via-exec.mjs").write_text("// stub\n", encoding="utf-8")
    (pw / "run-formprep-via-eform.mjs").write_text("// stub\n", encoding="utf-8")
    monkeypatch.setenv("AIRC_INSTALL_ROOT", str(root))
    monkeypatch.delenv("AIRC_PRIORITY_FORM_VIA_EFORM", raising=False)
    monkeypatch.setattr(
        ac._priority,
        "resolve_priority_worker_dir",
        lambda _r: root / "airc" / "priority-worker",
    )
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"] = list(argv)
        class P:
            returncode = 0
            stdout = '{"ok":true,"ended":true,"errors":[]}\n'
            stderr = ""
        return P()

    out = ac._priority_sdk_repprep(
        ename="ORDERS",
        path="FORMPREPDRCT2",
        form_prep=True,
        instance={
            "credentialTarget": "PriorityWeb/x",
            "company": "c",
            "url": "https://example.invalid",
            "user": "u",
        },
        cred_fetcher=lambda _t: "secret-placeholder-priority-pw",
        node_runner=fake_run,
    )
    assert out.get("ok") is True
    assert seen["argv"][1].replace("\\", "/").endswith(
        "priority-worker/sdk/run-repprep-via-exec.mjs"
    )
    assert seen["argv"][seen["argv"].index("--proc") + 1] == "FORMPREPDRCT2"


def test_fr5913_pack_always_runs_npm_ci():
    """FR #5913: do not skip npm ci when node_modules/priority-web-sdk already exists."""
    pack = PACK.read_text(encoding="utf-8")
    assert "FR #5913" in pack
    # Contiguous always-ci marker from the pack block.
    assert "always npm ci so a stale/partial node_modules cannot ship" in pack
    assert "npm not on PATH (required for priority-worker npm ci" in pack
    # Old skip-if-present path is gone (npm was only invoked inside that guard).
    assert "node_modules missing and npm not on PATH" not in pack
    # npm ci is unconditional: Get-Command npm is not nested under Test-Path $nm.
    block_start = pack.index("# FR #5283 / #5905")
    block = pack[block_start : block_start + 1800]
    npm_ci_at = block.index("npm ci --omit=dev")
    # Any Test-Path of $nm before npm ci would be the old skip guard.
    before = block[:npm_ci_at]
    assert "Test-Path -LiteralPath $nm" not in before


def test_fr5905_mjs_cli_emits_json_when_name_missing():
    """Wrapper emits JSON for missing --name without printing secrets."""
    import shutil

    node = os.environ.get("AIRC_PRIORITY_NODE") or os.environ.get("NODE_EXE") or "node"
    node_path = node if os.path.isfile(node) else shutil.which(node)
    if not node_path:
        pytest.skip("node not available")
    env = dict(os.environ)
    env["PRIORITY_SDK_PASSWORD"] = "secret-placeholder-pw"
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
    assert "secret-placeholder-pw" not in blob

def test_fr5905_mjs_walk_selftest_stub_sdk():
    """Hostile: walker fills name field without silent edits[0]; uses proc.message."""
    import shutil

    node = os.environ.get("AIRC_PRIORITY_NODE") or os.environ.get("NODE_EXE") or "node"
    node_path = node if os.path.isfile(node) else shutil.which(node)
    if not node_path:
        pytest.skip("node not available")
    selftest = PW / "sdk" / "run-repprep-walk-selftest.mjs"
    assert selftest.is_file()
    proc = subprocess.run(
        [node_path, str(selftest)],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(PW),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    payload = json.loads(lines[-1])
    assert payload.get("ok") is True
    assert payload.get("selftest") == "walk"

