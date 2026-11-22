"""FR #8695 / BOB-53: Agents > Priority configures mcp.ntsa.uk via grok mcp."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import REPO

WIN = sys.platform == "win32"
CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
needs_csc = pytest.mark.skipif(not (WIN and CSC.is_file()), reason="needs Windows + .NET Framework csc.exe")
PS = __import__("shutil").which("powershell.exe") or __import__("shutil").which("powershell")
DIALOGS = REPO / "bob" / "tray" / "dialogs"
URL = "https://mcp.ntsa.uk/mcp"

FAKE = r"""
using System;
using System.IO;
class FakeGrok {
  static int Main(string[] args) {
    string log = Environment.GetEnvironmentVariable("BOB_FAKE_GROK_LOG") ?? "";
    string mode = Environment.GetEnvironmentVariable("BOB_FAKE_GROK_MODE") ?? "kept";
    if (log.Length > 0) File.AppendAllText(log, string.Join(" ", args) + "\n");
    string joined = string.Join(" ", args);
    if (joined.IndexOf("mcp list") >= 0) {
      if (mode == "list-fail") return 2;
      if (mode == "absent") { Console.WriteLine("no servers"); return 0; }
      if (mode == "wrong") { Console.WriteLine("priority-catalog: https://evil.example/mcp"); return 0; }
      if (mode == "stdio") { Console.WriteLine("priority-catalog: stdio python server.py"); return 0; }
      Console.WriteLine("priority-catalog: https://mcp.ntsa.uk/mcp");
      return 0;
    }
    if (joined.IndexOf("mcp doctor") >= 0) {
      if (mode == "doctor-fail") { Console.WriteLine("handshake failed"); return 1; }
      Console.WriteLine("handshake OK");
      return 0;
    }
    return 0;
  }
}
"""


@pytest.fixture(scope="module")
def tray_exe(tmp_path_factory) -> Path:
    if not (WIN and CSC.is_file() and PS):
        pytest.skip("needs Windows + csc.exe + powershell")
    out = tmp_path_factory.mktemp("bob53dlg")
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(REPO / "bob" / "scripts" / "Build-BobDialogs.ps1"),
         "-RepoRoot", str(REPO), "-OutDir", str(out)],
        capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    return out / "bob-tray.exe"


@pytest.fixture(scope="module")
def fake_grok(tmp_path_factory) -> Path:
    if not (WIN and CSC.is_file()):
        pytest.skip("needs Windows + csc.exe")
    folder = tmp_path_factory.mktemp("fakegrok")
    src = folder / "fake.cs"
    src.write_text(FAKE, encoding="utf-8")
    exe = folder / "grok.exe"
    r = subprocess.run([str(CSC), "/nologo", "/out:" + str(exe), str(src)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return exe


def _run(exe: Path, root: Path, fake: Path, mode: str) -> dict:
    log = root / "grok-args.txt"
    out = root / "snap.json"
    env = dict(os.environ)
    env["PATH"] = str(fake.parent) + os.pathsep + env.get("PATH", "")
    env["USERPROFILE"] = str(root / "empty-profile")
    env["BOB_FAKE_GROK_MODE"] = mode
    env["BOB_FAKE_GROK_LOG"] = str(log)
    (root / "empty-profile").mkdir(exist_ok=True)
    p = subprocess.Popen(
        [str(exe), "--root", str(root), "--priority-mcp-configure", str(out)],
        env=env)
    assert p.wait(timeout=60) == 0
    snap = json.loads(out.read_text(encoding="utf-8"))
    args = log.read_text(encoding="utf-8") if log.is_file() else ""
    snap["_args"] = args
    return snap


def test_source_snapshot_has_no_environment_dump():
    src = (DIALOGS / "BobTray.cs").read_text(encoding="utf-8-sig")
    writer = src.split("public static void WriteSnapshot", 1)[1].split("static string Json", 1)[0]
    assert "GetEnvironmentVariable" not in writer
    assert "priorityMcpUrl" in src
    assert URL in src
    for key in ('\\"name\\"', '\\"url\\"', '\\"state\\"', '\\"doctor\\"', '\\"doctorMessage\\"', '\\"ts\\"', '\\"version\\"'):
        assert key in writer


def test_shipped_default_pins_priority_mcp_url():
    doc = json.loads((REPO / "bob" / "tray" / "config" / "default.json").read_text(encoding="utf-8-sig"))
    assert doc["priorityMcpUrl"] == URL


def test_reject_non_host_url_uses_constant():
    src = (DIALOGS / "BobTray.cs").read_text(encoding="utf-8-sig")
    assert 'Host, "mcp.ntsa.uk"' in src
    assert "reject url" in src


@needs_csc
def test_absent_adds_exact_url(tray_exe, fake_grok, tmp_path):
    snap = _run(tray_exe, tmp_path, fake_grok, "absent")
    assert snap["state"] == "added"
    assert snap["url"] == URL
    assert snap["doctor"] == "ok"
    assert "mcp add --transport http priority-catalog " + URL in snap["_args"]
    assert "handshake" not in json.dumps({k: snap[k] for k in snap if k != "_args"}) or snap["doctorMessage"]


@needs_csc
def test_kept_does_not_add(tray_exe, fake_grok, tmp_path):
    snap = _run(tray_exe, tmp_path, fake_grok, "kept")
    assert snap["state"] == "kept"
    assert snap["doctor"] == "ok"
    assert "mcp add" not in snap["_args"]


@needs_csc
def test_wrong_url_does_not_add(tray_exe, fake_grok, tmp_path):
    snap = _run(tray_exe, tmp_path, fake_grok, "wrong")
    assert snap["state"] == "wrong"
    assert snap["doctor"] == "skipped"
    assert "mcp add" not in snap["_args"]
    assert "evil.example" not in snap["url"]


@needs_csc
def test_stdio_is_wrong(tray_exe, fake_grok, tmp_path):
    snap = _run(tray_exe, tmp_path, fake_grok, "stdio")
    assert snap["state"] == "wrong"
    assert "mcp add" not in snap["_args"]


@needs_csc
def test_list_failed_does_not_add(tray_exe, fake_grok, tmp_path):
    snap = _run(tray_exe, tmp_path, fake_grok, "list-fail")
    assert snap["state"] == "list-failed"
    assert snap["doctor"] == "skipped"
    assert "mcp add" not in snap["_args"]


@needs_csc
def test_doctor_failed(tray_exe, fake_grok, tmp_path):
    snap = _run(tray_exe, tmp_path, fake_grok, "doctor-fail")
    assert snap["state"] == "kept"
    assert snap["doctor"] == "failed"


@needs_csc
def test_bad_shipped_url_falls_back(tray_exe, fake_grok, tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "default.json").write_text('{"priorityMcpUrl":"https://evil.example/mcp"}', encoding="utf-8")
    snap = _run(tray_exe, tmp_path, fake_grok, "absent")
    assert snap["url"] == URL
    assert "evil.example" not in snap["_args"]


@needs_csc
def test_grok_missing(tray_exe, tmp_path):
    out = tmp_path / "snap.json"
    env = dict(os.environ)
    env["PATH"] = str(tmp_path)
    env["USERPROFILE"] = str(tmp_path / "noprof")
    (tmp_path / "noprof").mkdir()
    p = subprocess.Popen(
        [str(tray_exe), "--root", str(tmp_path), "--priority-mcp-configure", str(out)],
        env=env)
    assert p.wait(timeout=60) == 0
    snap = json.loads(out.read_text(encoding="utf-8"))
    assert snap["state"] == "grok-missing"
    assert snap["doctor"] == "skipped"
    assert set(snap) == {"name", "url", "state", "doctor", "doctorMessage", "ts", "version"}
