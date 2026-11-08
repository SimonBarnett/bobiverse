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
    assert c.write_project_dir(tmp_path, line, env) == recorded
    assert not (tmp_path / "opencode-project-dir.txt").exists()


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
    assert "opencode-project-dir.txt" not in script
    assert "@@BOBJOB1|" in script
    assert "[char]9" not in script
    assert "Invoke-OpencodeRun $prompt '' ''" in script
    inbound = script.split("function Invoke-OpencodeInbound", 1)[1]
    bare = inbound.find("Invoke-OpencodeRun $raw '' ''")
    assert inbound.find("job-context-malformed") < bare
    assert inbound.find("Get-OpencodeFromJobKeys") < bare
    assert "Split-OpencodeFrame" in script
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
    with pytest.raises(c.WorktreeBaseError):
        c.job_worktree_base({"BOB_JOB_WORKTREE_BASE": r"D:\ai\.."}, disks=disks)
    with pytest.raises(c.WorktreeBaseError):
        c.job_worktree_base({"BOB_JOB_WORKTREE_BASE": r"D:\ai\worktrees\..\.."}, disks=disks)
    nested = c.job_worktree_base({"BOB_JOB_WORKTREE_BASE": r"D:\ai\worktrees\extra\.."}, disks=disks)
    assert nested.replace("/", "\\").rstrip("\\").lower() == "d:\\ai\\worktrees"
    assert c.canonicalize_path(r"D:\ai\..").replace("/", "\\") == "D:\\"
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
    assert c.prepare_opencode_wire(line, env)["wire"] == ""
    slash = "FROM jeeves #marchhare n: FR ../bobiverse#2 https://x"
    assert c.classify_opencode_job(slash, env)["state"] == "malformed"
    secret = "FROM jeeves #marchhare n: FR bobiverse#3 https://x"
    blocked = c.classify_opencode_job(secret, {"BOB_JOB_WORKTREE_BASE": "C:/passwords"})
    assert blocked["state"] == "forbidden"
    assert "opencode-dir-forbidden" in blocked["nack"]
    assert c.write_project_dir(tmp_path, secret, {"BOB_JOB_WORKTREE_BASE": "C:/passwords"}) == ""


def test_standing_prompt_example_is_not_a_job():
    prompt = bw.worker_prompt(r"C:\ai\bob\worker", r"C:\run", "marchhare", "marchhare-1")
    assert "FR SimonBarnett/a-search#637" in prompt
    assert c.message_job_keys(prompt) == []
    decision = c.classify_opencode_job(prompt, {})
    assert decision["state"] == "not_assign"
    assert decision["nack"] == ""
    wire = c.prepare_opencode_wire(prompt, {})
    assert wire["wire"] == prompt
    assert c.parse_opencode_frame(prompt) is None
    inbound = c.decode_opencode_inbound(bw.one_line(prompt))
    assert inbound["action"] == "run" and inbound["nack"] == "" and inbound["run"] is True


def test_job_frame_survives_inject_console_one_line_and_a_broken_frame_does_not_run(tmp_path: Path):
    import inspect

    source = inspect.getsource(bw.inject_console)
    assert source.index("one_line(text)") < source.index('os.name != "nt"')
    env = {"BOB_BRIDGE_HOME": str(tmp_path / "bridge")}
    first = "FROM jeeves #marchhare n: FR SimonBarnett/bobiverse#6147 https://x"
    second = "FROM jeeves #marchhare n: FR SimonBarnett/bobiverse#99 https://x" + (" tail" * 200)
    for line in (first, second):
        Path(c.project_dir_for_assign(line, env)).mkdir(parents=True, exist_ok=True)
    wires = [c.prepare_opencode_wire(line, env) for line in (first, second)]
    decoded = [c.decode_opencode_inbound(bw.one_line(item["wire"])) for item in wires]
    assert decoded[0]["dir"] == wires[0]["path"]
    assert decoded[1]["dir"] == wires[1]["path"]
    assert decoded[0]["dir"] != decoded[1]["dir"]
    assert decoded[0]["key"] == "FR SimonBarnett/bobiverse#6147"
    assert decoded[1]["key"] == "FR SimonBarnett/bobiverse#99"
    assert decoded[1]["line"].startswith("FROM ")
    assert len(wires[1]["wire"]) > 600
    assert len(bw.one_line(wires[1]["wire"])) == 600
    tabbed = (
        "@@BOBJOB1\tFR SimonBarnett/bobiverse#6147\t"
        + wires[0]["path"]
        + "\t"
        + first
    )
    broken = c.decode_opencode_inbound(bw.one_line(tabbed))
    assert "\t" not in bw.one_line(tabbed)
    assert broken["action"] == "nack" and broken["run"] is False
    assert broken["key"] == "FR SimonBarnett/bobiverse#6147"
    assert "job-context-malformed" in broken["nack"]
    naked = c.decode_opencode_inbound(bw.one_line(first))
    assert naked["action"] == "nack" and naked["run"] is False
    assert naked["key"] == "FR SimonBarnett/bobiverse#6147"
    lost = c.decode_opencode_inbound("@@BOBJOB1 not a frame")
    assert lost["action"] == "nack" and lost["run"] is False


def test_two_assigns_keep_separate_directories(tmp_path: Path):
    env = {"BOB_BRIDGE_HOME": str(tmp_path / "bridge")}
    first = "FROM jeeves #marchhare n: FR SimonBarnett/bobiverse#6147 https://x"
    second = "FROM jeeves #marchhare n: FR SimonBarnett/bobiverse#99 https://x"
    path = Path(c.project_dir_for_assign(first, env))
    path2 = Path(c.project_dir_for_assign(second, env))
    path.mkdir(parents=True)
    path2.mkdir(parents=True)
    one = c.prepare_opencode_wire(first, env)
    two = c.prepare_opencode_wire(second, env)
    frame_one = c.parse_opencode_frame(one["wire"])
    frame_two = c.parse_opencode_frame(two["wire"])
    assert frame_one is not None and frame_two is not None
    assert frame_one["line"] == first and frame_two["line"] == second
    assert frame_one["dir"] == one["path"] and frame_two["dir"] == two["path"]
    assert frame_one["dir"] != frame_two["dir"]
    assert frame_one["key"] == "FR SimonBarnett/bobiverse#6147"
    assert "@@BOBJOB1" not in frame_one["line"]
    assert "--auto" not in one["wire"] and "OPENCODE_CONFIG" not in one["wire"]
    carried_one = c.decode_opencode_inbound(bw.one_line(one["wire"]))
    carried_two = c.decode_opencode_inbound(bw.one_line(two["wire"]))
    assert carried_one["action"] == "project" and carried_one["run"] is True
    assert carried_two["action"] == "project" and carried_two["run"] is True
    assert carried_one["key"] == frame_one["key"] and carried_one["dir"] == frame_one["dir"]
    assert carried_two["key"] == frame_two["key"] and carried_two["dir"] == frame_two["dir"]
    assert carried_one["dir"] != carried_two["dir"]
    assert carried_one["line"].startswith("FROM ")
    assert "@@BOBJOB1" not in carried_one["line"]


def test_missing_dir_nacks_and_existing_dir_is_framed(tmp_path: Path):
    env = {"BOB_BRIDGE_HOME": str(tmp_path / "bridge")}
    first = "FROM jeeves #marchhare n: FR SimonBarnett/bobiverse#6147 https://x"
    missing = c.classify_opencode_job(first, env)
    assert missing["state"] == "absent"
    assert missing["nack"] == "NACK FR SimonBarnett/bobiverse#6147 worktree-absent (FR #6240)"
    assert c.prepare_opencode_wire(first, env)["wire"] == ""
    path = Path(c.project_dir_for_assign(first, env))
    path.mkdir(parents=True)
    ready = c.prepare_opencode_wire(first, env)
    assert ready["state"] == "project" and ready["nack"] == ""
    assert c.parse_opencode_frame(ready["wire"])["dir"] == ready["path"]
    args = c.opencode_run_args("opencode/beam-free", "hello", ready["path"])
    assert args[:3] == ["run", "--dir", str(Path(ready["path"]).resolve())]
    assert "--auto" not in args


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
    path = Path(c.project_dir_for_assign(bw.format_from("jeeves", "#marchhare", text), env))
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


def test_post_ack_refusal_allows_the_same_assign_after_the_dir_returns(tmp_path: Path):
    written: list[str] = []
    injected: list[str] = []
    relay = bw.Relay(log=lambda *_a, **_k: None, outbox_path=tmp_path / "outbox.txt", clock=lambda: 0.0)
    relay.write_outbox = lambda text: written.append(text) or True
    state = {"vanish": True}

    def inject(line: str) -> bool:
        if state["vanish"]:
            state["vanish"] = False
            raise bw.JobContextRefused(
                "NACK FR SimonBarnett/bobiverse#6147 worktree-absent (FR #6240)"
            )
        injected.append(line)
        return True

    relay.set_target(inject)
    env = {"BOB_BRIDGE_HOME": str(tmp_path / "bridge")}
    relay.opencode_job_block = lambda line: c.opencode_job_context_nack(line, env)
    text = "marchhare-22088: FR SimonBarnett/bobiverse#6147 https://x"
    path = Path(c.project_dir_for_assign(bw.format_from("jeeves", "#marchhare", text), env))
    path.mkdir(parents=True)
    status = relay.deliver("jeeves", "#marchhare", text)
    assert status == "opencode_job_blocked"
    assert injected == []
    assert any(item.startswith("ACK ") for item in written)
    assert any("worktree-absent" in item for item in written)
    written.clear()
    status_retry = relay.deliver("jeeves", "#marchhare", text)
    assert status_retry == "injected"
    assert injected
    assert any(item.startswith("ACK ") for item in written)
    refused = tmp_path / "opencode-job-refused.txt"
    refused.write_text("FR SimonBarnett/bobiverse#6147\n", encoding="utf-8")
    written.clear()
    injected.clear()
    status_file = relay.deliver("jeeves", "#marchhare", text)
    assert status_file == "injected"
    assert injected
    assert not refused.exists()


def test_two_jobs_in_one_flood_are_rejected_without_ack(tmp_path: Path):
    written: list[str] = []
    injected: list[str] = []
    relay = bw.Relay(log=lambda *_a, **_k: None, outbox_path=tmp_path / "outbox.txt", clock=lambda: 0.0, max_burst=1)
    relay.write_outbox = lambda text: written.append(text) or True
    relay.set_target(lambda line: injected.append(line) or True)
    env = {"BOB_BRIDGE_HOME": str(tmp_path / "bridge")}
    relay.opencode_job_block = lambda line: c.opencode_job_context_nack(line, env)
    for number in (1, 2, 3):
        text = f"marchhare-22088: FR SimonBarnett/bobiverse#{number} https://x"
        path = Path(c.project_dir_for_assign(bw.format_from("jeeves", "#marchhare", text), env))
        path.mkdir(parents=True)
    first = relay.deliver("jeeves", "#marchhare", "marchhare-22088: FR SimonBarnett/bobiverse#1 https://x")
    second = relay.deliver("jeeves", "#marchhare", "marchhare-22088: FR SimonBarnett/bobiverse#2 https://x")
    third = relay.deliver("jeeves", "#marchhare", "marchhare-22088: FR SimonBarnett/bobiverse#3 https://x")
    assert first == "injected"
    assert second == "coalescing" and third == "coalescing"
    if relay._timer is not None:
        relay._timer.cancel()
    relay._flush_overflow()
    assert not any(item.startswith("ACK FR SimonBarnett/bobiverse#2") for item in written)
    assert not any(item.startswith("ACK FR SimonBarnett/bobiverse#3") for item in written)
    assert any("NACK FR SimonBarnett/bobiverse#2 job-context-ambiguous" in item for item in written)
    assert any("NACK FR SimonBarnett/bobiverse#3 job-context-ambiguous" in item for item in written)
    assert not any("flood-coalesced" in line for line in injected)
    both = (
        "FROM jeeves #marchhare marchhare-22088: FR SimonBarnett/bobiverse#3 https://a "
        "FR SimonBarnett/bobiverse#4 https://b"
    )
    written.clear()
    injected.clear()
    status = relay.deliver("jeeves", "#marchhare", "marchhare-22088: FR SimonBarnett/bobiverse#3 https://a FR SimonBarnett/bobiverse#4 https://b")
    assert status == "opencode_job_blocked"
    assert injected == []
    assert any(item.startswith("NACK FR SimonBarnett/bobiverse#3 job-context-ambiguous") for item in written)
    assert any(item.startswith("NACK FR SimonBarnett/bobiverse#4 job-context-ambiguous") for item in written)
    assert not any(item.startswith("ACK ") for item in written)
    assert c.message_job_keys(both) == [
        "FR SimonBarnett/bobiverse#3",
        "FR SimonBarnett/bobiverse#4",
    ]


def test_start_agent_refuses_opencode_when_gh_auth_is_missing(monkeypatch):
    monkeypatch.setattr(bw, "probe_gh_auth", lambda *_a, **_k: (True, c.GH_BLOCK_MESSAGE))
    sup = bw.Supervisor.__new__(bw.Supervisor)
    sup.kind = "opencode"
    sup.log = lambda *_a, **_k: None
    assert sup.start_agent() is False

def test_opencode_job_block_callback_is_opencode_only():
    """Grok/Cursor must not inherit OpenCode multi-key / flood NACK wiring."""
    relay = bw.Relay(log=lambda *_a, **_k: None)
    for kind, expect in (("opencode", True), ("grok", False), ("cursor", False)):
        sup = bw.Supervisor.__new__(bw.Supervisor)
        sup.kind = kind
        relay.opencode_job_block = (
            sup._opencode_job_block if (sup.kind or "").strip().lower() == "opencode" else None
        )
        assert (relay.opencode_job_block is not None) is expect


def test_grok_relay_without_opencode_job_block_keeps_multi_key_assign(tmp_path: Path):
    written: list[str] = []
    injected: list[str] = []
    relay = bw.Relay(log=lambda *_a, **_k: None, outbox_path=tmp_path / "outbox.txt")
    relay.write_outbox = lambda text: written.append(text) or True
    relay.set_target(lambda line: injected.append(line) or True)
    relay.opencode_job_block = None
    status = relay.deliver(
        "jeeves",
        "#redqueen",
        "redqueen-1: FR SimonBarnett/bobiverse#3 https://a FR SimonBarnett/bobiverse#4 https://b",
    )
    assert status == "injected"
    assert injected
    assert any(item.startswith("ACK FR SimonBarnett/bobiverse#3") for item in written)
    assert not any("job-context-ambiguous" in item for item in written)


def test_grok_flood_coalesce_when_opencode_job_block_unset(tmp_path: Path):
    injected: list[str] = []
    relay = bw.Relay(
        log=lambda *_a, **_k: None,
        outbox_path=tmp_path / "outbox.txt",
        clock=lambda: 0.0,
        max_burst=1,
    )
    relay.write_outbox = lambda text: True
    relay.set_target(lambda line: injected.append(line) or True)
    relay.opencode_job_block = None
    assert relay.deliver("jeeves", "#redqueen", "redqueen-1: FR SimonBarnett/bobiverse#1 https://x") == "injected"
    assert relay.deliver("jeeves", "#redqueen", "redqueen-1: FR SimonBarnett/bobiverse#2 https://x") == "coalescing"
    if relay._timer is not None:
        relay._timer.cancel()
    relay._flush_overflow()
    assert any("flood-coalesced" in line for line in injected)

