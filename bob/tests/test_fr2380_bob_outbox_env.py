"""FR #2380: seat outbox survives compaction via env + FROM footer (not ear home\\outbox)."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


def test_seat_env_extra_sets_bob_outbox_shop_nick(tmp_path: Path):
    run = tmp_path / "worker-marchhare-40208-ac2cf015"
    env = bw.seat_env_extra(run, "marchhare", "marchhare-40208")
    assert env["BOB_OUTBOX"] == str(run / "outbox.txt")
    assert env["BOB_SHOP"] == "#marchhare"
    assert env["BOB_NICK"] == "marchhare-40208"
    assert env["BOB_MACHINE"] == "marchhare"
    assert "home\\outbox.txt" not in env["BOB_OUTBOX"].replace("/", "\\").lower()


def test_worker_prompt_names_bob_outbox_and_forbids_ear_home(tmp_path: Path):
    run = tmp_path / "run" / "worker-x"
    text = bw.worker_prompt(str(tmp_path / "worker"), str(run), "marchhare", "marchhare-1")
    assert "$env:BOB_OUTBOX" in text or "BOB_OUTBOX" in text
    assert str(run / "outbox.txt") in text
    assert "home\\outbox.txt" in text  # explicit NEVER the ear path


def test_format_from_appends_outbox_footer():
    out = r"C:\Users\Administrator\AppData\Local\Bobiverse\worker\run\worker-x\outbox.txt"
    line = bw.format_from(
        "Jeeves",
        "#marchhare",
        "marchhare-40208: FR SimonBarnett/bobiverse#2380 https://github.com/SimonBarnett/bobiverse/issues/2380",
        outbox=out,
    )
    assert line.startswith("FROM Jeeves #marchhare ")
    assert "[outbox: " in line
    assert out in line
    # Idempotent if already present
    again = bw.format_from("Jeeves", "#marchhare", "x " + f"[outbox: {out}]", outbox=out)
    assert again.count("[outbox:") == 1


def test_relay_injects_outbox_footer_from_persist_dir(tmp_path: Path):
    logs: list[str] = []
    got: list[str] = []

    def inject(line: str) -> bool:
        got.append(line)
        return True

    relay = bw.Relay(logs.append, persist_dir=tmp_path)
    relay.set_target(inject)
    status = relay.deliver(
        "Jeeves",
        "#marchhare",
        "marchhare-1: FR SimonBarnett/bobiverse#1 https://example/issues/1",
    )
    assert status == "injected"
    assert got and "[outbox:" in got[0]
    assert str(tmp_path / "outbox.txt") in got[0]
    last = (tmp_path / "last-from.txt").read_text(encoding="utf-8")
    assert "[outbox:" in last


def test_compaction_survival_resolves_outbox_from_env_alone(tmp_path: Path, monkeypatch):
    """Agent context without first instruction must still resolve the run-dir outbox."""
    run = tmp_path / "worker-marchhare-40208-ac2cf015"
    run.mkdir(parents=True)
    (run / "outbox.txt").write_text("", encoding="utf-8")
    env = bw.seat_env_extra(run, "marchhare", "marchhare-40208")
    monkeypatch.setenv("BOB_OUTBOX", env["BOB_OUTBOX"])
    # Simulate "lost first instruction": only env remains.
    resolved = Path(__import__("os").environ["BOB_OUTBOX"])
    assert resolved == run / "outbox.txt"
    assert resolved.is_file()
    # Must not point at a bob install home outbox.
    assert "bob\\home\\outbox" not in str(resolved).replace("/", "\\").lower()
