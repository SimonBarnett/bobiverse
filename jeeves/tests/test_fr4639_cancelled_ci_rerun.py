"""FR #4639: re-run cancelled PASSed CI; expire pruned ci_fix; report fix_dup."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

mrb_merge_on_green = importlib.import_module("mrb_merge_on_green")
gitclaim = importlib.import_module("gitclaim")

SHA = "a" * 40
REPO = "SimonBarnett/a-search"


def _home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    return home


def _pr(num: int, *, checks: str, run_id: str = "", behind: bool = False) -> dict:
    pr = {
        "number": num,
        "title": "tip",
        "body": f"Closes {REPO}#1",
        "html_url": f"https://github.com/{REPO}/pull/{num}",
        "state": "open",
        "draft": False,
        "auto_merge": {"merge_method": "merge"},
        "head": {"sha": SHA},
        "user": {"login": "u"},
        "checks": checks,
        "run_id": run_id,
    }
    if behind:
        pr["behind_main"] = True
    return pr


def test_cancelled_resync_reruns_once_and_queues_no_fix(tmp_path, monkeypatch, capsys):
    home = _home(tmp_path)
    monkeypatch.setattr(
        mrb_merge_on_green, "main_branch_checks_red", lambda *_a, **_k: False
    )
    monkeypatch.setattr(mrb_merge_on_green, "_gh_token", lambda token=None: "FAKE_TOKEN")
    calls: list[tuple[str, str]] = []

    def fake_json(url, *, token, method="GET", body=None):
        calls.append((method, url))
        return {}

    monkeypatch.setattr(mrb_merge_on_green, "_gh_json", fake_json)
    mrb_merge_on_green.enqueue(
        home,
        repo=REPO,
        pr="2311",
        pass_sha=SHA,
        url=f"https://github.com/{REPO}/pull/2311",
    )
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": []},
    )
    pr = _pr(2311, checks="cancelled", run_id="9001")

    def fetch_json(url: str):
        if "/pulls" in url and "state=closed" not in url:
            return [pr]
        if "/issues" in url:
            return []
        return []

    first = gitclaim.resync_from_github(home, [REPO], fetch_json=fetch_json)
    assert first.get("ok") is True
    fixes = [
        r
        for r in gitclaim.load_unaccepted(home)
        if isinstance(r, dict) and str(r.get("task") or "").upper() == "FIX"
    ]
    assert fixes == []
    assert len(calls) == 1
    assert calls[0][0] == "POST"
    assert calls[0][1].endswith("/actions/runs/9001/rerun")
    second = gitclaim.resync_from_github(home, [REPO], fetch_json=fetch_json)
    assert second.get("ok") is True
    assert len(calls) == 1
    out = capsys.readouterr().out
    assert "resync rerun cancelled CI" in out
    assert "result=pending" in out


def test_cancelled_resync_reads_run_id_from_check_runs(tmp_path, monkeypatch, capsys):
    """Live pulls have no run_id. The workflow id is on the check-run details_url."""
    home = _home(tmp_path)
    monkeypatch.setattr(
        mrb_merge_on_green, "main_branch_checks_red", lambda *_a, **_k: False
    )
    monkeypatch.setattr(mrb_merge_on_green, "_gh_token", lambda token=None: "FAKE_TOKEN")
    calls: list[tuple[str, str]] = []

    def fake_json(url, *, token, method="GET", body=None):
        calls.append((method, url))
        return {}

    monkeypatch.setattr(mrb_merge_on_green, "_gh_json", fake_json)
    mrb_merge_on_green.enqueue(
        home,
        repo=REPO,
        pr="2311",
        pass_sha=SHA,
        url=f"https://github.com/{REPO}/pull/2311",
    )
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": []},
    )
    pr = _pr(2311, checks="cancelled", run_id="")

    def fetch_json(url: str):
        if url.endswith(f"/commits/{SHA}/check-runs"):
            return {
                "check_runs": [
                    {
                        "conclusion": "cancelled",
                        "details_url": (
                            "https://github.com/SimonBarnett/a-search/actions/runs/9001/job/1"
                        ),
                    }
                ]
            }
        if "/pulls" in url and "state=closed" not in url:
            return [pr]
        return []

    gitclaim.resync_from_github(home, [REPO], fetch_json=fetch_json)
    assert len(calls) == 1
    assert calls[0][0] == "POST"
    assert calls[0][1].endswith("/actions/runs/9001/rerun")


def test_behind_mergeable_state_updates_branch(tmp_path, monkeypatch):
    home = _home(tmp_path)
    monkeypatch.setattr(
        mrb_merge_on_green, "main_branch_checks_red", lambda *_a, **_k: False
    )
    monkeypatch.setattr(mrb_merge_on_green, "_gh_token", lambda token=None: "FAKE_TOKEN")
    calls: list[tuple[str, str]] = []

    def fake_json(url, *, token, method="GET", body=None):
        calls.append((method, url))
        return {}

    monkeypatch.setattr(mrb_merge_on_green, "_gh_json", fake_json)
    mrb_merge_on_green.enqueue(
        home,
        repo=REPO,
        pr="2311",
        pass_sha=SHA,
        url=f"https://github.com/{REPO}/pull/2311",
    )
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": []},
    )
    pr = _pr(2311, checks="cancelled", run_id="")
    pr["mergeable_state"] = "behind"

    def fetch_json(url: str):
        if "/pulls" in url and "state=closed" not in url:
            return [pr]
        return []

    gitclaim.resync_from_github(home, [REPO], fetch_json=fetch_json)
    assert len(calls) == 1
    assert calls[0][0] == "PUT"
    assert calls[0][1].endswith("/pulls/2311/update-branch")


def test_pruned_ci_fix_without_done_offers_again(tmp_path: Path):
    home = _home(tmp_path)
    first = mrb_merge_on_green.enqueue_fix_ci(
        home,
        repo=REPO,
        pr="2311",
        pass_sha=SHA,
        detail="failure",
        main_red=False,
        now_epoch=1_000.0,
    )
    assert first == "added"
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": []},
    )
    second = mrb_merge_on_green.enqueue_fix_ci(
        home,
        repo=REPO,
        pr="2311",
        pass_sha=SHA,
        detail="failure",
        main_red=False,
        now_epoch=2_000.0,
    )
    assert second == "added"


def test_resync_summary_counts_fix_dup(tmp_path, monkeypatch, capsys):
    home = _home(tmp_path)
    monkeypatch.setattr(
        mrb_merge_on_green, "main_branch_checks_red", lambda *_a, **_k: False
    )
    mrb_merge_on_green.enqueue(
        home,
        repo=REPO,
        pr="2317",
        pass_sha=SHA,
        url=f"https://github.com/{REPO}/pull/2317",
    )
    pr = _pr(2317, checks="failure")

    def fetch_json(url: str):
        if "/pulls" in url and "state=closed" not in url:
            return [pr]
        if "/issues" in url:
            return []
        return []

    gitclaim.resync_from_github(home, [REPO], fetch_json=fetch_json)
    again = gitclaim.resync_from_github(home, [REPO], fetch_json=fetch_json)
    assert int(again.get("fix_dup") or 0) == 1
    capsys.readouterr()


def test_github_resync_ok_line_names_fix_dup():
    text = (
        ROOT / "common" / "scripts" / "chair_health.py"
    ).read_text(encoding="utf-8")
    assert "fix_dup={res.get('fix_dup', 0)}" in text
