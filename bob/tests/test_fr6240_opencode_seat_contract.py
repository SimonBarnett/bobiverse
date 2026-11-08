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
    assert "Write-OpencodeJobNack" in script
    assert "job-context-malformed" in script
    assert "answer external_directory" not in script
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
    assert "no evidence that an interactive Allow" in text


def test_unset_env_uses_data_drive_default_and_refuses_a_drive_root():
    disks = [
        {"Root": "C:\\", "DriveType": 3},
        {"Root": "D:\\", "DriveType": 3},
        {"Root": "E:\\", "DriveType": 2},
    ]
    base = c.job_worktree_base({}, disks=disks, system_drive="C:")
    assert base.replace("/", "\\").rstrip("\\").lower() == "d:\\ai\\worktrees"
    only_sys = c.job_worktree_base(
        {}, disks=[{"Root": "C:\\", "DriveType": 3}], system_drive="C:"
    )
    assert only_sys.replace("/", "\\").rstrip("\\").lower() == "c:\\ai\\worktrees"
    other = c.job_worktree_base(
        {},
        disks=[{"Root": "D:\\", "DriveType": 2}, {"Root": "E:\\", "DriveType": 3}],
        system_drive="C:",
    )
    assert other.replace("/", "\\").rstrip("\\").lower() == "e:\\ai\\worktrees"
    with pytest.raises(c.WorktreeBaseError):
        c.job_worktree_base({"BOB_JOB_WORKTREE_BASE": "D:\\"}, disks=disks)
    with pytest.raises(c.WorktreeBaseError):
        c.job_worktree_base({"BOB_BRIDGE_HOME": "C:/"}, disks=disks)
    line = "FROM jeeves #marchhare n: FR bobiverse#6147 https://x"
    recorded = c.project_dir_for_assign(line, {}, disks=disks, system_drive="C:")
    norm = recorded.replace("/", "\\").lower()
    assert norm == "d:\\ai\\worktrees\\bobiverse\\fr-6147"


def test_malformed_assign_nacks_and_writes_nothing(tmp_path: Path):
    env = {"BOB_BRIDGE_HOME": str(tmp_path / "bridge")}
    line = "FROM jeeves #marchhare n: FR ..#1 https://x"
    decision = c.classify_opencode_job(line, env)
    assert decision["state"] == "malformed"
    assert decision["nack"] == "NACK FR ..#1 job-context-malformed (FR #6240)"
    assert c.write_project_dir(tmp_path, line, env) == ""
    assert not (tmp_path / "opencode-project-dir.txt").exists()
    slash = "FROM jeeves #marchhare n: FR ../bobiverse#2 https://x"
    assert c.classify_opencode_job(slash, env)["state"] == "malformed"
    secret = "FROM jeeves #marchhare n: FR bobiverse#3 https://x"
    blocked = c.classify_opencode_job(secret, {"BOB_JOB_WORKTREE_BASE": "C:/passwords"})
    assert blocked["state"] == "forbidden"
    assert "opencode-dir-forbidden" in blocked["nack"]
    assert c.write_project_dir(tmp_path, secret, {"BOB_JOB_WORKTREE_BASE": "C:/passwords"}) == ""


def test_missing_dir_nacks_before_any_record_and_existing_dir_replaces_it(tmp_path: Path):
    env = {"BOB_BRIDGE_HOME": str(tmp_path / "bridge")}
    first = "FROM jeeves #marchhare n: FR SimonBarnett/bobiverse#6147 https://x"
    missing = c.classify_opencode_job(first, env)
    assert missing["state"] == "absent"
    assert missing["nack"] == "NACK FR SimonBarnett/bobiverse#6147 worktree-absent (FR #6240)"
    assert c.record_opencode_job(tmp_path, first, env)["nack"] == missing["nack"]
    assert not (tmp_path / "opencode-project-dir.txt").exists()
    path = Path(c.project_dir_for_assign(first, env))
    path.mkdir(parents=True)
    ready = c.record_opencode_job(tmp_path, first, env)
    assert ready["state"] == "project" and ready["nack"] == ""
    assert (tmp_path / "opencode-project-dir.txt").read_text(encoding="utf-8").strip() == str(path)
    second = "FROM jeeves #marchhare n: FR SimonBarnett/bobiverse#99 https://x"
    assert c.classify_opencode_job(second, env)["state"] == "absent"
    assert (tmp_path / "opencode-project-dir.txt").read_text(encoding="utf-8").strip() == str(path)
    path2 = Path(c.project_dir_for_assign(second, env))
    path2.mkdir(parents=True)
    moved = c.record_opencode_job(tmp_path, second, env)
    assert moved["state"] == "project"
    assert (tmp_path / "opencode-project-dir.txt").read_text(encoding="utf-8").strip() == str(path2)
    args = c.opencode_run_args("opencode/beam-free", "hello", str(path2))
    assert args[:3] == ["run", "--dir", str(path2.resolve())]
    assert "--auto" not in args
    assert "OPENCODE_CONFIG" not in args


def test_relay_nacks_missing_worktree_before_ack_and_accepts_a_later_one(tmp_path: Path):
    written: list[str] = []
    injected: list[str] = []
    relay = bw.Relay(log=lambda *_a, **_k: None, outbox_path=tmp_path / "outbox.txt")
    relay.write_outbox = lambda text: written.append(text) or True
    relay.set_target(lambda line: injected.append(line) or True)
    env = {"BOB_BRIDGE_HOME": str(tmp_path / "bridge")}
    relay.opencode_job_block = lambda line: c.opencode_job_context_nack(line, env)
    text = "marchhare-22088: FR SimonBarnett/bobiverse#6147 https://x"
    status = relay.deliver("jeeves", "#marchhare", text)
    assert status == "opencode_job_blocked"
    assert injected == []
    assert any(item.startswith("NACK FR SimonBarnett/bobiverse#6147 worktree-absent") for item in written)
    assert not any(item.startswith("ACK ") for item in written)
    status_again = relay.deliver("jeeves", "#marchhare", text)
    assert status_again == "opencode_job_blocked"
    assert not any(item.startswith("ACK ") for item in written)
    path = Path(c.project_dir_for_assign("FR SimonBarnett/bobiverse#6147 https://x", env))
    path.mkdir(parents=True)
    written.clear()
    status_ok = relay.deliver("jeeves", "#marchhare", text)
    assert status_ok == "injected"
    assert injected
    assert any(item.startswith("ACK FR SimonBarnett/bobiverse#6147") for item in written)
    assert not any("worktree-absent" in item for item in written)


def test_held_missing_worktree_is_nacked_instead_of_injected(tmp_path: Path):
    written: list[str] = []
    injected: list[str] = []
    relay = bw.Relay(log=lambda *_a, **_k: None)
    relay.write_outbox = lambda text: written.append(text) or True
    relay.set_target(lambda line: injected.append(line) or True)
    env = {"BOB_BRIDGE_HOME": str(tmp_path / "bridge")}
    relay.opencode_job_block = lambda line: c.opencode_job_context_nack(line, env)
    relay._pending.append(
        "FROM jeeves #marchhare marchhare-22088: FR SimonBarnett/bobiverse#7 https://x"
    )
    assert relay.release_held_assigns() == 0
    assert injected == []
    assert any("worktree-absent" in item for item in written)
    assert not any(item.startswith("ACK ") for item in written)


def test_start_agent_refuses_opencode_when_gh_auth_is_missing(monkeypatch):
    monkeypatch.setattr(bw, "probe_gh_auth", lambda *_a, **_k: (True, c.GH_BLOCK_MESSAGE))
    sup = bw.Supervisor.__new__(bw.Supervisor)
    sup.kind = "opencode"
    sup.log = lambda *_a, **_k: None
    assert sup.start_agent() is False
