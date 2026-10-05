"""FR #2379: harvest receipt must tolerate intake responses with no url key (StrictMode)."""
from __future__ import annotations

import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from repo_layout import ROOT

HARVEST = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"
REPORT = ROOT / "scripts" / "Report-BobiverseIntakeIssue.ps1"


def test_fr2379_harvest_script_uses_safe_receipt_props():
    text = HARVEST.read_text(encoding="utf-8-sig")
    assert "FR #2379" in text
    assert "Get-IntakeResponseProp" in text
    # Receipt line must not interpolate bare $r.url under StrictMode.
    idx = text.index("HARVESTED intake_id=")
    chunk = text[idx : idx + 200]
    assert "$r.url" not in chunk
    assert "$r.queued" not in chunk
    assert "Get-IntakeResponseProp" in text[text.index("function Get-IntakeResponseProp") : idx + 200]


def test_fr2379_report_script_uses_safe_receipt_props():
    text = REPORT.read_text(encoding="utf-8-sig")
    assert "FR #2379" in text
    # Successful return must not read bare $resp.url under StrictMode.
    assert "$resp.url" not in text
    assert "Get-IntakeResponseProp" in text or "PSObject.Properties" in text


def test_fr2379_harvest_receipt_missing_url_is_harvested_not_queued(tmp_path: Path):
    """Live POST returns 202 without url → HARVESTED, no false outbox queue."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            return

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            _ = self.rfile.read(length)
            body = json.dumps({"intake_id": "in_fr2379test", "queued": False}).encode("utf-8")
            self.send_response(202)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    outbox = tmp_path / "harvest-outbox"
    outbox.mkdir()
    try:
        r = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(HARVEST),
                "-Summary",
                "FR #2379 receipt missing url must not false-queue",
                "-Lesson",
                "StrictMode-safe intake receipt props.",
                "-OutboxDir",
                str(outbox),
                "-IntakeUrl",
                f"http://127.0.0.1:{port}/bob/v1/intake",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(ROOT),
        )
    finally:
        httpd.shutdown()

    assert r.returncode == 0, r.stdout + r.stderr
    assert "HARVESTED" in r.stdout, r.stdout + r.stderr
    assert "in_fr2379test" in r.stdout
    assert "QUEUED" not in r.stdout
    assert "property 'url'" not in (r.stdout + r.stderr).lower()
    assert list(outbox.glob("*.json")) == []


def test_fr2379_files_end_with_newline():
    assert HARVEST.read_bytes().endswith(b"\n")
    assert Path(__file__).read_bytes().endswith(b"\n")
