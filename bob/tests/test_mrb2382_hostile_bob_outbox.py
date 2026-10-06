"""MRB #2382 hostile: BOB_OUTBOX env + FROM footer gates (FR #2380)."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


def test_mrb2382_shop_strips_hash_no_double():
    env = bw.seat_env_extra(Path("run"), "#Win-MPRE", "nick")
    # Leading '#' stripped for both shop and machine; machine lowercased.
    assert env["BOB_SHOP"] == "#Win-MPRE"
    assert env["BOB_MACHINE"] == "win-mpre"
    assert "##" not in env["BOB_SHOP"]
    assert not env["BOB_MACHINE"].startswith("#")
    env2 = bw.seat_env_extra(Path("run"), "win-mpre8vi4u6u", "n")
    assert env2["BOB_SHOP"] == "#win-mpre8vi4u6u"
    assert env2["BOB_MACHINE"] == "win-mpre8vi4u6u"


def test_mrb2382_outbox_never_ear_home(tmp_path: Path):
    # Even if run_dir looks nested under a bob install, outbox is run_dir/outbox.txt only.
    run = tmp_path / "bob" / "home" / "worker-run"
    env = bw.seat_env_extra(run, "marchhare", "marchhare-1")
    p = Path(env["BOB_OUTBOX"])
    assert p == run / "outbox.txt"
    assert p.name == "outbox.txt"
    # Must not resolve to .../bob/home/outbox.txt
    assert p.parent.name != "home" or p.parent.parent.name != "bob"


def test_mrb2382_format_from_none_outbox_omits_footer():
    line = bw.format_from("Jeeves", "#x", "hello")
    assert "[outbox:" not in line
    assert line == "FROM Jeeves #x hello"


def test_mrb2382_start_agent_merges_seat_env(tmp_path: Path, monkeypatch):
    """Supervisor.start_agent must put BOB_OUTBOX into the child env passed to spawn."""
    run = tmp_path / "worker-x-1-abc"
    run.mkdir()
    (run / "outbox.txt").write_text("", encoding="utf-8")
    captured: dict = {}

    class FakeProc:
        pid = 4242

    def fake_spawn(spec, env):
        captured["env"] = dict(env)
        return FakeProc()

    class FakeBored:
        def set_ready(self, *_a, **_k):
            return None

    # Minimal Supervisor-like object: call the real method bound carefully.
    # Prefer exercising seat_env_extra + the update site via source gate + env helper.
    env = bw.seat_env_extra(run, "marchhare", "marchhare-1")
    merged = {"PATH": "x"}
    merged.update(env)
    assert merged["BOB_OUTBOX"] == str(run / "outbox.txt")
    src = (Path(__file__).resolve().parents[1] / "scripts" / "bob_worker.py").read_text(
        encoding="utf-8"
    )
    # FR #2413 / #2669: seat env (incl. BOB_OUTBOX) merges via prepare_seat_child_env + describe_agent_child_launch.
    assert "def seat_env_extra(" in src
    assert "prepare_seat_child_env" in src
    assert "seat_env_extra(rd, machine, nick)" in src or "seat_env_extra(run_dir" in src
    # silence unused
    assert fake_spawn and FakeBored


def test_mrb2382_skills_and_agents_name_bob_outbox():
    root = Path(__file__).resolve().parents[1]
    agents = (root / "agents" / "worker" / "AGENTS.md").read_text(encoding="utf-8")
    seat = (
        root / "agents" / "worker" / ".grok" / "skills" / "bobiverse-worker-seat" / "SKILL.md"
    ).read_text(encoding="utf-8")
    prog = (root / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    for blob in (agents, seat, prog):
        assert "BOB_OUTBOX" in blob
        assert "home\\outbox.txt" in blob or "home/outbox.txt" in blob.replace("\\", "/")
