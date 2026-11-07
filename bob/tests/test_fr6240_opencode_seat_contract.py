"""FR #6240: OpenCode launch contract. No credential reads, no --auto."""
from __future__ import annotations

import json
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


def test_permission_config_allows_only_the_run_directory():
    cfg = c.permission_config(RUN)
    rules = cfg["permission"]["external_directory"]
    assert rules["*"] == "ask"
    allow = [k for k, v in rules.items() if v == "allow"]
    assert allow == [RUN + "\\*"]
    assert ".config\\gh" not in json.dumps(cfg)
    assert "--auto" not in json.dumps(cfg)
    with pytest.raises(ValueError):
        c.permission_config(r"C:\Users\Administrator\.config\gh")


def test_opencode_dir_refuses_credential_paths_and_omits_auto():
    assert c.dir_is_forbidden(r"C:\Users\Administrator\.config\gh") is True
    assert c.dir_is_forbidden(r"C:\passwords\token.txt") is True
    assert c.dir_is_forbidden(WT) is False
    plain = c.opencode_run_args("opencode/beam-free", "hello", "")
    assert plain[:3] == ["run", "-m", "opencode/beam-free"]
    assert "--auto" not in plain
    assert "--interactive" not in plain
    directed = c.opencode_run_args("opencode/beam-free", "hello", WT)
    assert directed[:3] == ["run", "--dir", WT]
    assert "--auto" not in directed
    with pytest.raises(ValueError):
        c.opencode_run_args("opencode/beam-free", "hello", r"C:\Users\Administrator\.config\gh")


def test_generated_wrapper_binds_dir_and_outbox_without_bypass(tmp_path: Path):
    spec = bw.build_launch(
        "opencode", "agent", r"C:\ai\bob\worker", "keep ticking",
        r"C:\opencode.exe", tmp_path,
    )
    script = next(v for k, v in spec.files.items() if str(k).endswith("launch-opencode.ps1"))
    cfg_name = "opencode-seat.json"
    cfg = next(v for k, v in spec.files.items() if str(k).endswith(cfg_name))
    parsed = json.loads(cfg)
    rules = parsed["permission"]["external_directory"]
    assert rules["*"] == "ask"
    assert any(k.endswith("\\*") and v == "allow" and ".config\\gh" not in k for k, v in rules.items())
    assert "$argList = @('run', '-m', $model, $line)" in script
    assert "'run', '--dir', $ocDir" in script
    assert "opencode --auto is forbidden" in script
    assert "'--interactive'" not in script
    assert "has no --interactive flag" in script
    assert "OPENCODE_CONFIG" in script
    assert "Get-Content" not in script
    assert "git-credentials" in script
    assert "BOB_OPENCODE_DIR" in script


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
