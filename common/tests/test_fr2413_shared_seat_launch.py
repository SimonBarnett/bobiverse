"""FR #2413: tray vs CLI/remote share one seat launch path."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# bob/scripts + common/scripts
sys.path.insert(0, str(ROOT / "scripts"))
bob_scripts = ROOT.parent / "bob" / "scripts"
if bob_scripts.is_dir():
    sys.path.insert(0, str(bob_scripts))
common_scripts = ROOT  # when test lives in common/tests, scripts is sibling
# repo layout: common/tests -> common/scripts
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import seat_launch as sl  # noqa: E402


def test_tray_and_cli_contracts_equal(tmp_path):
    install = tmp_path / "bob"
    (install / "worker").mkdir(parents=True)
    (install / "plan").mkdir(parents=True)
    for mode in ("agent", "plan"):
        tray = sl.tray_launch_contract(mode, install, machine_id="ionos")
        cli = sl.cli_launch_contract(mode, install, machine_id="ionos")
        assert tray == cli
        assert tray["exe_name"] == "bob-worker.exe"
        assert tray["argv"][1:3] == ["--mode", mode]
        assert "--install-root" in tray["argv"]
        assert Path(tray["working_directory"]).name == ("plan" if mode == "plan" else "worker")
        if mode == "agent":
            assert "--machine-id" in tray["argv"]
            assert "ionos" in tray["argv"]
        else:
            assert "--machine-id" not in tray["argv"]


def test_shared_seat_plan_agent_env_and_prompt(tmp_path, monkeypatch):
    install = tmp_path / "bob"
    worker = install / "worker"
    worker.mkdir(parents=True)
    (worker / "AGENTS.md").write_text("x", encoding="utf-8")
    (worker / ".grok" / "skills").mkdir(parents=True)
    run = tmp_path / "run" / "agent-1"
    run.mkdir(parents=True)

    # Avoid importing full bob_worker if heavy; inject fns
    def prompt_fn(folder, run_dir, machine, nick):
        return f"PROMPT {folder} outbox={run_dir}/outbox.txt nick={nick}"

    def seat_env(run_dir, machine, nick):
        return {
            "BOB_OUTBOX": str(Path(run_dir) / "outbox.txt"),
            "BOB_SHOP": f"#{machine}",
            "BOB_NICK": nick,
            "BOB_MACHINE": machine,
        }

    plan = sl.shared_seat_plan(
        "agent",
        install,
        machine="ionos",
        nick="ionos-1",
        run_dir=run,
        prompt_fn=prompt_fn,
        seat_env_fn=seat_env,
    )
    assert plan.cwd == str(worker)
    assert plan.env_extra["BOB_OUTBOX"].endswith("outbox.txt")
    assert plan.env_extra["BOB_SHOP"] == "#ionos"
    assert "PROMPT" in plan.prompt
    assert plan.worker_argv == sl.worker_exe_argv("agent", install, machine_id="ionos")


def test_shared_seat_plan_plan_mode(tmp_path):
    install = tmp_path / "bob"
    (install / "plan").mkdir(parents=True)
    run = tmp_path / "run"
    run.mkdir()

    def prompt_fn(folder):
        return f"PLAN {folder}"

    plan = sl.shared_seat_plan(
        "plan",
        install,
        run_dir=run,
        prompt_fn=prompt_fn,
    )
    assert plan.cwd.endswith("plan")
    assert plan.env_extra == {}
    assert plan.prompt.startswith("PLAN ")


def test_remote_start_matches_tray_argv(tmp_path):
    """Remote !startworker ultimately calls Start-BobTrayWorkerExe — same argv as tray click."""
    install = tmp_path / "bob"
    (install / "worker").mkdir(parents=True)
    remote = sl.cli_launch_contract("agent", install, machine_id="marchhare")
    tray = sl.tray_launch_contract("agent", install, machine_id="marchhare")
    assert remote == tray
