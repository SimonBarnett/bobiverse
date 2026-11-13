"""MRB #7089 hostile: FR #7084 launch + config paths + cheapest idle offer must be wired."""
from __future__ import annotations

import json
from pathlib import Path

import bob_worker as bw
import gitclaim as gc
import worker_start_model as wsm


def test_mrb7089_loads_default_json_then_tray_models(tmp_path: Path, monkeypatch):
    root = tmp_path / "install"
    default = root / "tray" / "config" / "default.json"
    default.parent.mkdir(parents=True)
    default.write_text(
        json.dumps({"workerStartModels": {"grok": "EXAMPLE_FROM_DEFAULT"}}),
        encoding="utf-8",
    )
    local = tmp_path / "AppData" / "Bobiverse"
    local.mkdir(parents=True)
    (local / "tray-models.json").write_text(
        json.dumps({"workerStartModels": {"grok": "EXAMPLE_FROM_TRAY"}}),
        encoding="utf-8",
    )
    env = {
        "BOB_INSTALL_ROOT": str(root),
        "LOCALAPPDATA": str(tmp_path / "AppData"),
    }
    monkeypatch.delenv(wsm.ENV_CONFIG_PATH, raising=False)
    monkeypatch.delenv(wsm.ENV_CONFIG_JSON, raising=False)
    cfg = wsm.load_worker_start_config(env=env)
    assert cfg["workerStartModels"]["grok"] == "EXAMPLE_FROM_TRAY"


def test_mrb7089_build_launch_cursor_agent_includes_configured_model(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(
        wsm.ENV_CONFIG_JSON,
        json.dumps({"workerStartModels": {"cursor": "EXAMPLE_CURSOR_MIN"}}),
    )
    rd = tmp_path / "run"
    rd.mkdir()
    spec = bw.build_launch(
        "cursor",
        "agent",
        str(tmp_path / "cwd"),
        "prompt",
        r"C:\fake\cursor-agent.cmd",
        rd,
    )
    ps1 = next(Path(k) for k in spec.files if str(k).endswith("launch-cursor.ps1"))
    text = spec.files[str(ps1)] if str(ps1) in spec.files else spec.files[ps1]
    assert "--model" in text
    assert "EXAMPLE_CURSOR_MIN" in text
    assert "--model auto" not in text


def test_mrb7089_build_launch_grok_includes_configured_model(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(
        wsm.ENV_CONFIG_JSON,
        json.dumps({"workerStartModels": {"grok": "EXAMPLE_GROK_MIN"}}),
    )
    rd = tmp_path / "run"
    rd.mkdir()
    spec = bw.build_launch(
        "grok",
        "agent",
        str(tmp_path / "cwd"),
        "prompt",
        r"C:\fake\grok.exe",
        rd,
        session_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    )
    assert spec.argv[spec.argv.index("--model") + 1] == "EXAMPLE_GROK_MIN"


def test_mrb7089_cursor_launch_stamps_actual_env(tmp_path, monkeypatch):
    monkeypatch.setenv(
        wsm.ENV_CONFIG_JSON,
        json.dumps({"workerStartModels": {"cursor": "EXAMPLE_CURSOR_MIN"}}),
    )
    rd = tmp_path / "run"
    rd.mkdir()
    child = bw.describe_agent_child_launch(
        kind="cursor",
        mode="agent",
        cwd=str(tmp_path / "cwd"),
        run_dir=rd,
        machine="flamingo",
        nick="flamingo-1",
        agent_exe=r"C:\fake\cursor-agent.cmd",
        prompt="prompt",
    )
    assert child["env"].get(wsm.ENV_ACTUAL_MODEL) == "EXAMPLE_CURSOR_MIN"
    actual = wsm.actual_from_launch_spec("cursor", child["spec"], env=child["env"])
    assert actual == "EXAMPLE_CURSOR_MIN"
    assert wsm.model_mismatch(actual, "EXAMPLE_CURSOR_MIN") is False
    assert wsm.model_mismatch("EXAMPLE_CURSOR_MAX", "EXAMPLE_CURSOR_MIN") is True


def test_mrb7089_mismatch_seat_skipped(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    import bobreport

    (tmp_path / "registered-machines.json").write_text(
        '{"v":1,"machines":["flamingo"]}',
        encoding="utf-8",
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    doc = bobreport.empty_digest()
    doc["machines"]["flamingo"] = {
        "id": "flamingo",
        "online": True,
        "workers": {
            "99": {
                "pid": "99",
                "nick": "flamingo-99",
                "state": "idle",
                "start_model": "EXAMPLE_GROK_MAX",
                "configured_model": "EXAMPLE_GROK_MIN",
                "model_mismatch": True,
                "cost_tier": "max",
            }
        },
        "worker_list": [
            {
                "nick": "flamingo-99",
                "state": "idle",
                "start_model": "EXAMPLE_GROK_MAX",
                "configured_model": "EXAMPLE_GROK_MIN",
                "model_mismatch": True,
                "cost_tier": "max",
            }
        ],
    }
    bobreport.save_digest(tmp_path, doc)
    cand = {"task": "FR", "repo": "SimonBarnett/bobiverse", "id": "1"}
    assert gc._seat_model_allows_row(tmp_path, "flamingo-99", cand) is False


def test_mrb7089_pyinstaller_hides_worker_start_model():
    text = Path(__file__).resolve().parents[2].joinpath("bob", "scripts", "Build-BobWorker.ps1").read_text(
        encoding="utf-8"
    )
    assert "--hidden-import', 'worker_start_model'" in text or "worker_start_model" in text


def test_mrb7089_idle_seats_cheapest_first():
    rows = [
        {"nick": "max-1", "channel": "#m"},
        {"nick": "min-2", "channel": "#m"},
    ]
    fields = {
        "max-1": {"cost_tier": "max", "model_mismatch": False},
        "min-2": {"cost_tier": "min", "model_mismatch": False},
    }
    got = gc.sort_idle_seats_cheapest_first(rows, fields)
    assert [r["nick"] for r in got] == ["min-2", "max-1"]
