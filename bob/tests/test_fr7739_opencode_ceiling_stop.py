"""FR #7739: ceiling kill is reported once; a dead job stops the turn; no PR."""
from __future__ import annotations

import bob_worker as bw
import opencode_turn_guard as g


def test_fr7739_ceiling_reports_once():
    g._FILED.clear()
    calls: list[dict] = []

    def post(title, body, *, repo, sig, exe):
        calls.append({"title": title, "body": body, "repo": repo, "sig": sig, "exe": exe})

    first = g.report_opencode_hard_ceiling(
        "flamingo", "marchhare-28996", "FR SimonBarnett/bobiverse#7704", 1800000, "hard ceiling 1800000ms", filer_post=post
    )
    second = g.report_opencode_hard_ceiling(
        "flamingo", "marchhare-28996", "FR SimonBarnett/bobiverse#7704", 1800000, "hard ceiling 1800000ms", filer_post=post
    )
    assert first["posted"] is True
    assert second["skipped"] is True
    assert len(calls) == 1
    body = calls[0]["body"]
    assert "machine: flamingo" in body
    assert "seat: marchhare-28996" in body
    assert "job: FR SimonBarnett/bobiverse#7704" in body
    assert "elapsed_ms: 1800000" in body
    assert "reason: hard ceiling 1800000ms" in body
    assert calls[0]["sig"] == first["sig"]


def test_fr7739_stop_reason_closed_giveup_reassign():
    job = "FR SimonBarnett/bobiverse#7704"
    assert g.opencode_turn_stop_reason("CLOSED", "", job) == "closed"
    assert g.opencode_turn_stop_reason("OPEN", f"GIVEUP {job} jeeves\n", job) == "giveup"
    assert g.opencode_turn_stop_reason("OPEN", f"CANCEL {job}\n", job) == "giveup"
    assert g.opencode_turn_stop_reason("OPEN", "ASSIGN FR SimonBarnett/bobiverse#7726\n", job) == "reassigned"
    assert g.opencode_turn_stop_reason("OPEN", f"ACK {job}\n", job) == ""


def test_fr7739_watchdog_polls_under_60s(tmp_path: Path):
    spec = bw.build_launch("opencode", "agent", str(tmp_path), "hello", "opencode.exe", tmp_path)
    text = next(v for p, v in spec.files.items() if str(p).endswith("launch-opencode.ps1"))
    assert "$ocJobPoll % 50" in text or "($ocJobPoll % 50)" in text
    assert "Start-Sleep -Milliseconds 100" in text
    assert "job-ended" in text
    assert "ceiling" in text
    assert "opencode_turn_guard.py" in text
    # 50 polls * 100ms = 5s, inside the 60s acceptance window.
    assert 50 * 100 < 60000


def test_fr7739_auto_pr_skips_closed_issue(tmp_path: Path, monkeypatch):
    class _R:
        def __init__(self, code=0, out=""):
            self.returncode = code
            self.stdout = out
            self.stderr = ""

    created: list[list[str]] = []

    def run(argv, **kwargs):
        created.append(list(argv))
        if "--abbrev-ref" in argv:
            return _R(0, "fr-7739\n")
        if "rev-parse" in argv and argv[-1] == "HEAD":
            return _R(0, "abc123\n")
        if "status" in argv:
            return _R(0, "")
        if argv[-1] in ("origin/fr-7739", "@{u}"):
            return _R(0, "abc123\n")
        if "pr" in argv and "list" in argv:
            return _R(0, "[]\n")
        if "rev-list" in argv:
            return _R(0, "1\n")
        if "issue" in argv and "view" in argv:
            return _R(0, '{"state":"CLOSED"}\n')
        if "pr" in argv and "create" in argv:
            raise AssertionError("closed issue must not open a PR")
        return _R(1, "")

    url = bw.opencode_finish_auto_pr(tmp_path, "FR SimonBarnett/bobiverse#7739", run=run)
    assert url == ""
    assert not any("create" in a for a in created)


def test_fr7739_issue_view_failure_stays_open():
    class _R:
        def __init__(self, code=1, out=""):
            self.returncode = code
            self.stdout = out
            self.stderr = "nope"

    def run(argv, **kwargs):
        return _R(1, "")

    assert g.opencode_issue_is_open("SimonBarnett/bobiverse", "7739", run=run) is True
