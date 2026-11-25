"""FR #9837: Report-BobiverseIntakeIssue emits validated number + ISSUE_NUMBER= host lines."""
from __future__ import annotations

import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from repo_layout import ROOT

REPORT = ROOT / "scripts" / "Report-BobiverseIntakeIssue.ps1"
REPO = "SimonBarnett/bobiverse"
CANON = f"https://github.com/{REPO}/issues/9830"


def _run_report(port: int, title: str = "fr9837 probe") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            (
                f"& '{REPORT}' -Repo {REPO} -Kind fr "
                f"-Title '{title}' -Body 'probe' "
                f"-IntakeUrl 'http://127.0.0.1:{port}/bob/v1/intake' | "
                "ConvertTo-Json -Compress"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _parse_json(stdout: str) -> dict[str, Any]:
    out = (stdout or "").strip()
    start = out.find("{")
    assert start >= 0, out
    return json.loads(out[start:])


def _serve(body: dict[str, Any]):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            return

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            _ = self.rfile.read(length)
            raw = json.dumps(body).encode("utf-8")
            self.send_response(202)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, port


def test_fr9837_filed_number_and_host_lines():
    httpd, port = _serve(
        {
            "intake_id": "in_fr9837_filed",
            "queued": False,
            "number": 9830,
            "url": CANON,
            "action": "created",
        }
    )
    try:
        r = _run_report(port, "fr9837 filed")
    finally:
        httpd.shutdown()
    assert r.returncode == 0, r.stdout + r.stderr
    combined = (r.stdout or "") + "\n" + (r.stderr or "")
    doc = _parse_json(r.stdout or "")
    assert doc.get("ok") is True
    assert doc.get("number") == 9830
    assert isinstance(doc.get("number"), int)
    assert doc.get("action") == "created"
    assert f"ISSUE_NUMBER=9830" in combined
    assert f"ISSUE_URL={CANON}" in combined
    assert "ISSUE_PENDING" not in combined


def test_fr9837_url_only_derives_number():
    httpd, port = _serve(
        {
            "intake_id": "in_fr9837_url",
            "queued": False,
            "url": CANON,
        }
    )
    try:
        r = _run_report(port, "fr9837 url only")
    finally:
        httpd.shutdown()
    assert r.returncode == 0, r.stdout + r.stderr
    doc = _parse_json(r.stdout or "")
    assert doc.get("number") == 9830
    combined = (r.stdout or "") + "\n" + (r.stderr or "")
    assert "ISSUE_NUMBER=9830" in combined


def test_fr9837_queued_pending_no_number():
    httpd, port = _serve({"intake_id": "in_fr9837_q", "queued": True})
    try:
        r = _run_report(port, "fr9837 queued")
    finally:
        httpd.shutdown()
    assert r.returncode == 0, r.stdout + r.stderr
    doc = _parse_json(r.stdout or "")
    assert doc.get("number") is None
    assert doc.get("queued") is True
    combined = (r.stdout or "") + "\n" + (r.stderr or "")
    assert "ISSUE_PENDING intake_id=in_fr9837_q queued=True" in combined or (
        "ISSUE_PENDING intake_id=in_fr9837_q queued=true" in combined.lower()
    )
    assert "ISSUE_NUMBER=" not in combined


def test_fr9837_invalid_pairs_null_number():
    cases = [
        {"intake_id": "a", "number": 9830, "url": f"https://github.com/{REPO}/pull/9830"},
        {"intake_id": "b", "number": 1, "url": CANON},
        {"intake_id": "c", "number": 9830, "url": "https://github.com/other/repo/issues/9830"},
        {"intake_id": "d", "number": 9830, "url": CANON + "?x=1"},
        {"intake_id": "e", "number": 0, "url": ""},
    ]
    for body in cases:
        body = dict(body)
        body["queued"] = False
        httpd, port = _serve(body)
        try:
            r = _run_report(port, f"fr9837 bad {body['intake_id']}")
        finally:
            httpd.shutdown()
        assert r.returncode == 0, (body, r.stdout, r.stderr)
        doc = _parse_json(r.stdout or "")
        assert doc.get("number") is None, body
        combined = (r.stdout or "") + "\n" + (r.stderr or "")
        assert "ISSUE_PENDING" in combined
        assert "ISSUE_NUMBER=" not in combined


def test_fr9837_action_commented_forwarded():
    httpd, port = _serve(
        {
            "intake_id": "in_fr9837_c",
            "queued": False,
            "number": 9830,
            "url": CANON,
            "action": "commented",
        }
    )
    try:
        r = _run_report(port, "fr9837 commented")
    finally:
        httpd.shutdown()
    assert r.returncode == 0, r.stdout + r.stderr
    doc = _parse_json(r.stdout or "")
    assert doc.get("number") == 9830
    assert doc.get("action") == "commented"


def test_fr9837_dry_run_number_key_null():
    r = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            (
                f"& '{REPORT}' -Repo {REPO} -Kind fr "
                f"-Title 'fr9837 dry' -Body 'probe' -DryRun | ConvertTo-Json -Compress"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    doc = _parse_json(r.stdout or "")
    assert doc.get("dry_run") is True
    assert "number" in doc
    assert doc.get("number") is None
    assert "action" in doc
