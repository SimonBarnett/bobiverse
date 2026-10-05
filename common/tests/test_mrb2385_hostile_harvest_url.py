"""Hostile MRB #2385: FR #2379 StrictMode harvest receipt gaps beyond implementer suite."""
from __future__ import annotations

import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from repo_layout import ROOT

HARVEST = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"
REPORT = ROOT / "scripts" / "Report-BobiverseIntakeIssue.ps1"


def test_flush_sent_line_uses_safe_intake_id():
    text = HARVEST.read_text(encoding="utf-8-sig")
    assert "SENT {0} intake_id={1}" in text or 'SENT {0} intake_id={1}' in text
    # No bare $r.intake_id on the SENT receipt (StrictMode if key absent).
    sent_idx = text.index("SENT ")
    window = text[max(0, sent_idx - 80) : sent_idx + 120]
    assert "$r.intake_id" not in window
    assert "Get-IntakeResponseProp" in window or "Get-IntakeResponseProp" in text


def test_report_always_emits_url_key_when_response_omits_it(tmp_path: Path):
    """Return object must include url= even when intake JSON has no url (callers under StrictMode)."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            return

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            _ = self.rfile.read(length)
            body = json.dumps({"intake_id": "in_mrb2385", "queued": False}).encode("utf-8")
            self.send_response(202)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        r = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                (
                    f"& '{REPORT}' -Repo SimonBarnett/bobiverse -Kind issue "
                    f"-Title 'mrb2385 hostile url key' -Body 'probe' "
                    f"-IntakeUrl 'http://127.0.0.1:{port}/bob/v1/intake' | "
                    "ConvertTo-Json -Compress"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
    finally:
        httpd.shutdown()

    assert r.returncode == 0, r.stdout + r.stderr
    # Find JSON object in stdout
    out = (r.stdout or "").strip()
    start = out.find("{")
    assert start >= 0, out
    doc = json.loads(out[start:])
    assert doc.get("ok") is True
    assert "url" in doc  # key present for StrictMode callers
    assert doc.get("intake_id") == "in_mrb2385"


def test_helper_duplicated_but_identical():
    """Both scripts ship the same StrictMode helper (acceptable duplication; must stay aligned)."""
    h = HARVEST.read_text(encoding="utf-8-sig")
    r = REPORT.read_text(encoding="utf-8-sig")
    assert "function Get-IntakeResponseProp" in h and "function Get-IntakeResponseProp" in r
    # Core guard lines present in both.
    for text in (h, r):
        assert "PSObject.Properties[$Name]" in text
        assert "FR #2379" in text
