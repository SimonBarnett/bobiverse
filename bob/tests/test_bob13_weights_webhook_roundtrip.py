"""FR #8714 / BOB-13: Weights form binds to GET/PUT /bob/v1/models (no local store)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from repo_layout import REPO

WIN = sys.platform == "win32"
CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
PS = shutil.which("powershell.exe") or shutil.which("powershell") or shutil.which("pwsh")

WEIGHTS = REPO / "bob" / "tray" / "dialogs" / "WeightsForm.cs"
CLIENT = REPO / "bob" / "tray" / "dialogs" / "BobModelsClient.cs"
TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
BUILD = REPO / "bob" / "scripts" / "Build-BobDialogs.ps1"

REQUIRED = (
    "Plan",
    "Priority",
    "Jeeves",
    "Grok",
    "Cursor",
    "Opencode",
    "Opencode-Free",
)

FAKE_TOKEN = "FAKE_BOB13_MODELS_TOKEN_EXAMPLE_NOT_REAL"


def _default_agents(**overrides: dict) -> dict:
    rows = []
    for agent, cli in (
        ("Plan", "Grok"),
        ("Priority", "Grok"),
        ("Jeeves", "Grok"),
        ("Grok", "Grok"),
        ("Cursor", "Cursor"),
        ("Opencode", "Opencode"),
        ("Opencode-Free", "Opencode"),
    ):
        row = {
            "agent": agent,
            "cli": cli,
            "model": "",
            "context": "",
            "effort": "",
        }
        if agent in overrides:
            row.update(overrides[agent])
        rows.append(row)
    return {"agents": rows}


class _ModelsHandler(BaseHTTPRequestHandler):
    store: dict | None = None
    fail_next: bool = False

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/bob/v1/models":
            self.send_response(404)
            self.end_headers()
            return
        if _ModelsHandler.fail_next:
            self.send_response(503)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            body = b'{"error":"busy"}'
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = json.dumps(_ModelsHandler.store or _default_agents(), separators=(",", ":")).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_PUT(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/bob/v1/models":
            self.send_response(404)
            self.end_headers()
            return
        if _ModelsHandler.fail_next:
            self.send_response(503)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            body = b'{"error":"busy"}'
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b""
        try:
            doc = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self.send_response(400)
            body = b'{"error":"malformed JSON"}'
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        agents = doc.get("agents") if isinstance(doc, dict) else None
        if not isinstance(agents, list) or len(agents) != len(REQUIRED):
            self.send_response(400)
            body = b'{"error":"missing agents"}'
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        _ModelsHandler.store = {"agents": agents}
        # BOB-02: 204 when content changed.
        self.send_response(204)
        self.end_headers()


def _serve() -> tuple[HTTPServer, str]:
    httpd = HTTPServer(("127.0.0.1", 0), _ModelsHandler)
    _ModelsHandler.store = _default_agents()
    _ModelsHandler.fail_next = False
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    host, port = httpd.server_address
    return httpd, f"http://{host}:{port}/bob/v1/models"


def _build_tray(tmp_path: Path) -> Path:
    out_dir = tmp_path / "dlg"
    r = subprocess.run(
        [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(BUILD),
            "-RepoRoot",
            str(REPO),
            "-OutDir",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert r.returncode == 0, r.stdout + "\n" + r.stderr
    exe = out_dir / "bob-tray.exe"
    assert exe.is_file()
    return exe


def test_bob13_sources_pin_no_local_store():
    w = WEIGHTS.read_text(encoding="utf-8-sig")
    c = CLIENT.read_text(encoding="utf-8-sig")
    t = TRAY.read_text(encoding="utf-8-sig")
    b = BUILD.read_text(encoding="utf-8-sig")
    assert "BobModelsClient" in w
    assert "BeginSave" in w or "weightsSave" in w
    assert "tray-models.json" not in w
    assert "worker_start_model" not in w
    assert "BOB_MODELS_URL" in c
    assert "modelsUrl" in c
    assert "/bob/v1/models" in c
    assert "PUT" in c
    assert "--weights-get" in t
    assert "--weights-save" in t
    assert "BobModelsClient.cs" in b
    assert "weights_get" in t or "weights_get" in w
    assert "weights_save" in t or "weights_save" in w
    assert "weights_reload_match" in t or "weights_reload_match" in w


@pytest.mark.skipif(not (WIN and CSC.is_file() and PS), reason="needs Windows csc and powershell")
def test_bob13_weights_get_save_roundtrip_loopback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    httpd, url = _serve()
    try:
        monkeypatch.setenv("BOB_MODELS_URL", url)
        monkeypatch.setenv("BOB_MODELS_TOKEN", FAKE_TOKEN)
        # Isolate LOCALAPPDATA so a failure cannot touch the real tray-models.json.
        iso = tmp_path / "local"
        iso.mkdir()
        monkeypatch.setenv("LOCALAPPDATA", str(iso))

        tray = _build_tray(tmp_path)
        root = tmp_path / "root"
        root.mkdir()

        payload = _default_agents(Plan={"model": "build0.1", "context": "256", "effort": "medium"})
        save_in = tmp_path / "save-in.json"
        save_out = tmp_path / "save-out.json"
        save_in.write_text(json.dumps(payload), encoding="utf-8")

        p_save = subprocess.run(
            [
                str(tray),
                "--root",
                str(root),
                "--weights-save",
                str(save_in),
                "--text-out",
                str(save_out),
                "--no-engine",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            env=os.environ.copy(),
        )
        assert p_save.returncode == 0, p_save.stdout + p_save.stderr + save_out.read_text(encoding="utf-8")
        save_doc = json.loads(save_out.read_text(encoding="utf-8"))
        assert save_doc.get("ok") is True
        assert FAKE_TOKEN not in save_out.read_text(encoding="utf-8")
        assert FAKE_TOKEN not in (p_save.stdout or "")
        assert FAKE_TOKEN not in (p_save.stderr or "")

        get_out = tmp_path / "get-out.json"
        p_get = subprocess.run(
            [
                str(tray),
                "--root",
                str(root),
                "--weights-get",
                str(get_out),
                "--no-engine",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            env=os.environ.copy(),
        )
        assert p_get.returncode == 0, p_get.stdout + p_get.stderr
        get_doc = json.loads(get_out.read_text(encoding="utf-8"))
        assert get_doc.get("ok") is True
        plan = next(r for r in get_doc["agents"] if r["agent"] == "Plan")
        assert plan["model"] == "build0.1"
        assert plan["context"] == "256"
        assert plan["effort"] == "medium"
        assert [r["agent"] for r in get_doc["agents"]] == list(REQUIRED)
        assert FAKE_TOKEN not in get_out.read_text(encoding="utf-8")

        # Failure path: no tray-models.json under isolated LOCALAPPDATA.
        _ModelsHandler.fail_next = True
        fail_out = tmp_path / "fail-out.json"
        p_fail = subprocess.run(
            [
                str(tray),
                "--root",
                str(root),
                "--weights-get",
                str(fail_out),
                "--no-engine",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            env=os.environ.copy(),
        )
        assert p_fail.returncode != 0
        fail_doc = json.loads(fail_out.read_text(encoding="utf-8"))
        assert fail_doc.get("ok") is False
        tray_models = iso / "Bobiverse" / "tray-models.json"
        assert not tray_models.is_file()
        assert FAKE_TOKEN not in fail_out.read_text(encoding="utf-8")
    finally:
        httpd.shutdown()
        httpd.server_close()
