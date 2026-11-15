"""FR #7671: nonzero agent exit report quotes redacted stderr and dedupes on it."""
from __future__ import annotations

import json
import subprocess
import sys

import bob_worker as bw


def test_fr7671_fake_cli_stderr_is_in_the_report():
    proc = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stderr.write('failed to start the acp-agent-worker runtime\\n'); raise SystemExit(1)"],
        stderr=subprocess.PIPE,
    )
    ring, thread = bw.start_agent_stderr_capture(proc.stderr)
    assert proc.wait(timeout=20) == 1
    thread.join(timeout=2)
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=1,
        job_key="FR owner/repo#1",
        machine="seat",
        stderr_tail=ring.tail_text(),
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert "acp-agent-worker runtime" in posts[0]["body"]


def test_fr7671_secret_in_stderr_is_redacted():
    raw = "blocked password=EXAMPLEVALUE then continued\n"
    evidence = bw.agent_stderr_evidence(raw)
    assert "EXAMPLEVALUE" not in evidence
    assert "<redacted>" in evidence
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=1,
        job_key="FR owner/repo#9",
        machine="seat",
        stderr_tail=raw,
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    blob = json.dumps(posts[0])
    assert "EXAMPLEVALUE" not in blob


def test_fr7671_identical_crashes_share_one_dedupe_key():
    line = "failed to start the acp-agent-worker runtime: blocking pool pre-warm stalled"
    keys = []
    for job in ("FR owner/repo#1", "FR owner/repo#2"):
        bw.report_agent_cli_nonzero_exit(
            exit_code=1,
            job_key=job,
            machine="redqueen",
            stderr_tail=line + "\n",
            filer_post=lambda p: keys.append(p["idempotency_key"]) or {"ok": True},
        )
    assert keys[0] == keys[1]
    assert "repo#1" not in keys[0]
    assert "acp-agent-worker" in keys[0]
