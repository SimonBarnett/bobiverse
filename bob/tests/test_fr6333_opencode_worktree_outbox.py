"""FR #6333: OpenCode BOB_OUTBOX lives inside the job worktree (.bob/outbox.txt)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "bob" / "scripts"))

import bob_worker as bw  # noqa: E402
import opencode_seat_contract as c  # noqa: E402


def _init_clone(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "t@t"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "t"],
        check=True,
        capture_output=True,
    )
    (path / "README").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "README"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-m", "i"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "remote", "add", "origin", str(path)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "fetch", "origin", "main"],
        check=True,
        capture_output=True,
    )
    return path


def test_opencode_outbox_path_is_inside_worktree(tmp_path: Path):
    wt = tmp_path / "job"
    wt.mkdir()
    p = c.opencode_outbox_path(wt)
    assert p == wt / ".bob" / "outbox.txt"
    assert p.parent.parent == wt


def test_ensure_opencode_bob_outbox_creates_and_excludes(tmp_path: Path):
    clone = _init_clone(tmp_path / "clone")
    ob = c.ensure_opencode_bob_outbox(clone)
    assert ob.is_file()
    assert ob == clone / ".bob" / "outbox.txt"
    exclude = clone / ".git" / "info" / "exclude"
    assert exclude.is_file()
    lines = exclude.read_text(encoding="utf-8").splitlines()
    assert ".bob/" in lines
    st = subprocess.run(
        ["git", "-C", str(clone), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert ".bob" not in st.stdout


def test_exclude_bob_dir_idempotent(tmp_path: Path):
    clone = _init_clone(tmp_path / "clone")
    assert c.exclude_bob_dir_from_git(clone) is True
    assert c.exclude_bob_dir_from_git(clone) is True
    text = (clone / ".git" / "info" / "exclude").read_text(encoding="utf-8")
    assert text.count(".bob/") == 1


def test_ensure_job_worktree_stamps_outbox(tmp_path: Path):
    clone = _init_clone(tmp_path / "clone")
    base = tmp_path / "worktrees"
    env = {"BOB_JOB_WORKTREE_BASE": str(base), "BOB_REPO_CLONE_bobiverse": str(clone)}
    line = "FROM jeeves #marchhare n: FR SimonBarnett/bobiverse#6333 https://x"
    ready = c.ensure_opencode_job_worktree(line, env, install_root=str(clone))
    assert ready["state"] == "project"
    assert ready.get("outbox")
    ob = Path(ready["outbox"])
    assert ob.is_file()
    assert ob.name == "outbox.txt"
    assert ob.parent.name == ".bob"
    assert Path(ready["path"]) == ob.parent.parent


def test_outbox_line_allowed_filters_job_and_shape():
    key = "FR SimonBarnett/bobiverse#6333"
    shop = "#marchhare"
    assert c.opencode_outbox_line_allowed(
        "PRIVMSG #marchhare :DONE FR SimonBarnett/bobiverse#6333 https://example/pull/1",
        job_key=key,
        shop=shop,
    )
    assert c.opencode_outbox_line_allowed(
        "DONE FR SimonBarnett/bobiverse#6333 https://example/pull/1",
        job_key=key,
        shop=shop,
    )
    assert not c.opencode_outbox_line_allowed(
        "PRIVMSG #marchhare :DONE FR SimonBarnett/bobiverse#9999 https://x",
        job_key=key,
        shop=shop,
    )
    assert not c.opencode_outbox_line_allowed(
        "PRIVMSG #marchhare :hello world",
        job_key=key,
        shop=shop,
    )
    assert not c.opencode_outbox_line_allowed(
        "not a wire line",
        job_key=key,
        shop=shop,
    )
    assert not c.opencode_outbox_line_allowed(
        "PRIVMSG #other :DONE FR SimonBarnett/bobiverse#6333 https://x",
        job_key=key,
        shop=shop,
    )


def test_launch_script_sets_bob_outbox_inside_dir(tmp_path: Path):
    """launch-opencode.ps1 sets BOB_OUTBOX to <ocDir>\\.bob\\outbox.txt (FR #6333)."""
    spec = bw.build_launch(
        "opencode",
        "agent",
        r"C:\ai\bob\worker",
        "keep ticking",
        r"C:\opencode.exe",
        tmp_path,
    )
    script = next(v for k, v in spec.files.items() if str(k).endswith("launch-opencode.ps1"))
    assert "Join-Path $ocDir '.bob'" in script
    assert "Join-Path $bobDir 'outbox.txt'" in script
    assert "$env:BOB_OUTBOX" in script
    assert "opencode --auto is forbidden" in script
    assert "external_directory" not in script or "without external_directory" in script


def test_worker_prompt_names_in_worktree_outbox():
    text = bw.worker_prompt(r"C:\ai\bob\worker", r"C:\run", "marchhare", "marchhare-1")
    assert ".bob" in text
    assert "outbox.txt" in text
    assert "external_directory" in text.lower()


def test_may_send_outbox_forwards_done_keeps_other_job_nack(tmp_path: Path):
    """Run-dir may_send must not drop NACKs for a different job (MRB #6334)."""
    bored = bw.BoredEmitter(
        send=lambda: True,
        log=lambda *_a, **_k: None,
    )
    bored._ack_open = False

    sup = bw.Supervisor.__new__(bw.Supervisor)
    sup._opencode_job_key = "FR SimonBarnett/bobiverse#6333"
    sup._opencode_job_outbox = tmp_path / ".bob" / "outbox.txt"
    sup.machine = "marchhare"
    sup.irc = MagicMock()
    sup.irc.shop = "#marchhare"
    sup.bored = bored

    # Stale key must not block run-dir NACK for another job.
    assert (
        bw.Supervisor.may_send_outbox(
            sup, "NACK FR SimonBarnett/bobiverse#9999 worktree-create-failed:no-clone (FR #6240)"
        )
        is True
    )
    assert (
        bw.Supervisor.may_send_outbox(
            sup, "DONE FR SimonBarnett/bobiverse#6333 https://example/pull/9"
        )
        is True
    )


def test_may_send_job_outbox_filters_wrong_key(tmp_path: Path):
    bored = bw.BoredEmitter(
        send=lambda: True,
        log=lambda *_a, **_k: None,
    )
    bored._ack_open = True
    bored._ack_job_key = "FR SimonBarnett/bobiverse#6333"

    sup = bw.Supervisor.__new__(bw.Supervisor)
    sup._opencode_job_key = "FR SimonBarnett/bobiverse#6333"
    sup._opencode_job_outbox = tmp_path / ".bob" / "outbox.txt"
    sup.machine = "marchhare"
    sup.irc = MagicMock()
    sup.irc.shop = "#marchhare"
    sup.bored = bored

    assert (
        bw.Supervisor.may_send_job_outbox(
            sup, "DONE FR SimonBarnett/bobiverse#6333 https://example/pull/9"
        )
        is True
    )
    # FR #6472: may_send_job_outbox returns (False, reason) on refuse.
    assert bw.Supervisor.may_send_job_outbox(sup, "hello chatter") == (False, "malformed")
    assert bw.Supervisor.may_send_job_outbox(
        sup, "DONE FR SimonBarnett/bobiverse#1 https://x"
    ) == (False, "job-key mismatch")
    assert bw.Supervisor.may_send_job_outbox(
        sup, "ACK FR SimonBarnett/bobiverse#6333"
    ) == (False, "duplicate ACK")


def test_should_forward_dedupes_open_ack():
    bored = bw.BoredEmitter(
        send=lambda: True,
        log=lambda *_a, **_k: None,
    )
    bored._ack_open = True
    bored._ack_job_key = "FR SimonBarnett/bobiverse#6333"
    assert bored.should_forward_outbox("ACK FR SimonBarnett/bobiverse#6333") is False
    assert (
        bored.should_forward_outbox(
            "DONE FR SimonBarnett/bobiverse#6333 https://example/pull/1"
        )
        is True
    )


def test_drain_job_outbox_forwards_done(tmp_path: Path):
    job = tmp_path / "wt"
    job.mkdir()
    ob = c.ensure_opencode_bob_outbox(job)
    line = "PRIVMSG #marchhare :DONE FR SimonBarnett/bobiverse#6333 https://example/pull/1"
    ob.write_text(line + "\n", encoding="utf-8")

    said: list[tuple[str, str]] = []
    irc = MagicMock()
    irc.alive = True
    irc.shop = "#marchhare"
    irc.say = lambda target, text: said.append((target, text)) or True

    def may_send(payload: str) -> bool:
        return c.opencode_outbox_line_allowed(
            payload,
            job_key="FR SimonBarnett/bobiverse#6333",
            shop="#marchhare",
        )

    n = bw.drain_outbox(ob, irc, lambda *_: None, may_send=may_send)
    assert n >= 1
    assert any("DONE FR SimonBarnett/bobiverse#6333" in t for _, t in said)
    remaining = ob.read_text(encoding="utf-8") if ob.is_file() else ""
    assert "DONE FR" not in remaining


def test_drain_drops_malformed_via_may_send(tmp_path: Path):
    job = tmp_path / "wt"
    job.mkdir()
    ob = c.ensure_opencode_bob_outbox(job)
    ob.write_text(
        "PRIVMSG #marchhare :not-a-job-line\n"
        "PRIVMSG #marchhare :DONE FR SimonBarnett/bobiverse#9999 https://x\n",
        encoding="utf-8",
    )
    said: list[str] = []
    irc = MagicMock()
    irc.alive = True
    irc.shop = "#marchhare"
    irc.say = lambda target, text: said.append(text) or True

    def may_send(payload: str) -> bool:
        return c.opencode_outbox_line_allowed(
            payload,
            job_key="FR SimonBarnett/bobiverse#6333",
            shop="#marchhare",
        )

    bw.drain_outbox(ob, irc, lambda *_: None, may_send=may_send)
    assert said == []


def test_opencode_extra_outbox_paths():
    sup = bw.Supervisor.__new__(bw.Supervisor)
    sup._opencode_job_outbox = None
    assert bw.Supervisor.opencode_extra_outbox_paths(sup) == []
    p = Path("C:/tmp/wt/.bob/outbox.txt")
    sup._opencode_job_outbox = p
    assert bw.Supervisor.opencode_extra_outbox_paths(sup) == [p]


def test_no_auto_in_run_args_with_worktree(tmp_path: Path):
    args = c.opencode_run_args("opencode/beam-free", "hello", str(tmp_path))
    assert args[:3] == ["run", "--dir", str(tmp_path.resolve())]
    assert "--auto" not in args

def test_exclude_bob_dir_linked_worktree(tmp_path: Path):
    """Linked worktree exclude must write the common gitdir info/exclude (MRB #6334)."""
    clone = _init_clone(tmp_path / "clone")
    wt = tmp_path / "linked-wt"
    subprocess.run(
        ["git", "-C", str(clone), "worktree", "add", "-b", "fr-6333-test", str(wt), "origin/main"],
        check=True,
        capture_output=True,
    )
    ob = c.ensure_opencode_bob_outbox(wt)
    assert ob.is_file()
    common_exclude = clone / ".git" / "info" / "exclude"
    assert common_exclude.is_file()
    assert ".bob/" in common_exclude.read_text(encoding="utf-8").splitlines()
    st = subprocess.run(
        ["git", "-C", str(wt), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert ".bob" not in st.stdout


def test_outbox_loop_skips_missing_extra(tmp_path: Path, monkeypatch):
    """Missing worktree outbox must not be recreated by drain (MRB #6334)."""
    run_ob = tmp_path / "run" / "outbox.txt"
    run_ob.parent.mkdir(parents=True)
    run_ob.write_text("", encoding="utf-8")
    missing = tmp_path / "gone" / ".bob" / "outbox.txt"
    stop = __import__("threading").Event()
    irc = MagicMock()
    irc.alive = True

    def drain(path, *a, **k):
        if Path(path) == missing:
            raise AssertionError("must not drain missing extra")

    monkeypatch.setattr(bw, "drain_outbox", drain)
    monkeypatch.setattr(bw, "ensure_outbox", lambda p: None)

    def wait_once(timeout):
        stop.set()
        return True

    stop.wait = wait_once  # type: ignore
    bw.outbox_loop(
        run_ob,
        irc,
        stop,
        lambda *_: None,
        extra_paths=lambda: [missing],
    )
    assert not missing.exists()

