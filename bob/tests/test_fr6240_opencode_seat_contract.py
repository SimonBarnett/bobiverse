"""FR #6240: OpenCode launch contract. No credential reads, no --auto."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "bob" / "scripts"))

import bob_worker as bw  # noqa: E402
import opencode_seat_contract as c  # noqa: E402

RUN = r"C:\Users\Administrator\AppData\Local\Bobiverse\worker\run\worker-marchhare-22088-7dc94d5a"
WT = r"C:\Users\Administrator\.grok\bob-bridge\worktrees\bobiverse\fr-6147"


def test_gh_missing_blocks_without_reading_a_store():
    class Proc:
        returncode = 1
        stdout = ""
        stderr = "To get started with GitHub CLI, please run: gh auth login\n"

    seen = {}

    def run(cmd, **_k):
        seen["cmd"] = list(cmd)
        return Proc()

    blocked, msg = c.probe_gh_auth(run)
    assert seen["cmd"] == ["gh", "auth", "status"]
    assert blocked is True
    assert "gh auth login" in msg
    assert "hosts.yml" in msg
    assert "ghp_" not in msg


def test_gh_logged_in_does_not_echo_the_status_body():
    class Proc:
        returncode = 0
        stdout = "Logged in to github.com account bob (key ghp_SECRETVALUE)\n"
        stderr = ""

    blocked, msg = c.probe_gh_auth(lambda *_a, **_k: Proc())
    assert blocked is False
    assert msg == ""
    assert "ghp_" not in msg


def test_credential_paths_cover_slashes_and_symlink_targets(tmp_path: Path):
    assert c.dir_is_forbidden(r"C:\Users\Administrator\.config\gh") is True
    assert c.dir_is_forbidden("C:/Users/Administrator/.config/gh") is True
    assert c.dir_is_forbidden(r"C:\passwords\token.txt") is True
    assert c.dir_is_forbidden("C:/passwords") is True
    assert c.dir_is_forbidden(WT) is False
    secret = tmp_path / "real" / ".config" / "gh"
    secret.mkdir(parents=True)
    link = tmp_path / "looks-fine"
    link.symlink_to(secret, target_is_directory=True)
    assert c.dir_is_forbidden(str(link)) is True
    assert list(secret.iterdir()) == []


def test_job_dir_is_per_assign_and_blocks_until_the_folder_exists(tmp_path: Path):
    env = {"BOB_BRIDGE_HOME": str(tmp_path / "bob-bridge")}
    line = "FROM jeeves #marchhare marchhare-22088: FR SimonBarnett/bobiverse#6147 https://example"
    recorded = c.project_dir_for_assign(line, env)
    assert recorded.endswith("bobiverse/fr-6147") or recorded.endswith("bobiverse\\fr-6147")
    assert c.resolve_project_dir("")["state"] == "no_job"
    absent = c.resolve_project_dir(recorded)
    assert absent["blocked"] is True and absent["state"] == "absent"
    assert "not a completed job" in absent["message"]
    assert "Do not pass --auto" in absent["message"]
    folder = Path(recorded)
    folder.mkdir(parents=True)
    ready = c.resolve_project_dir(recorded)
    assert ready["blocked"] is False and ready["state"] == "project"
    args = c.opencode_run_args("opencode/beam-free", "hello", recorded)
    assert args[:3] == ["run", "--dir", ready["dir"]]
    assert "--auto" not in args
    assert c.write_project_dir(tmp_path, line, {}) == ""
    written = c.write_project_dir(tmp_path, line, env)
    assert (tmp_path / "opencode-project-dir.txt").read_text(encoding="utf-8").strip() == written


def test_generated_wrapper_does_not_grant_external_directory(tmp_path: Path):
    spec = bw.build_launch(
        "opencode", "agent", r"C:\ai\bob\worker", "keep ticking",
        r"C:\opencode.exe", tmp_path,
    )
    script = next(v for k, v in spec.files.items() if str(k).endswith("launch-opencode.ps1"))
    assert not any(str(k).endswith("opencode-seat.json") for k in spec.files)
    assert "external_directory" not in script or "allow" not in script
    assert '"allow"' not in script
    assert "OPENCODE_CONFIG" not in script
    assert "BOB_OPENCODE_DIR" not in script
    assert "opencode-project-dir.txt" in script
    assert "$argList = @('run', '-m', $model, $line)" in script
    assert "'run', '--dir', $ocDir" in script
    assert "blocked worktree_absent" in script
    assert "opencode --auto is forbidden" in script
    assert "'--interactive'" not in script
    assert "Get-Content" not in script


def test_worker_prompt_is_windows_native_and_blocks_credential_hunt():
    text = bw.worker_prompt(r"C:\ai\bob\worker", r"C:\run", "marchhare", "marchhare-1")
    assert "Select-String" in text
    assert "Do not run Unix grep or head" in text
    assert "gh auth login" in text
    assert "hosts.yml" in text
    assert "--auto" in text
    assert "Do not pass --auto" in text
    assert "BOB_HOME may be empty" in text


def test_start_agent_refuses_opencode_when_gh_auth_is_missing(monkeypatch):
    monkeypatch.setattr(bw, "probe_gh_auth", lambda *_a, **_k: (True, c.GH_BLOCK_MESSAGE))
    sup = bw.Supervisor.__new__(bw.Supervisor)
    sup.kind = "opencode"
    sup.log = lambda *_a, **_k: None
    assert sup.start_agent() is False
