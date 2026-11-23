"""BOB-22 / FR #8720: Cursor launch dry-run cites the Cursor webhook row."""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import models_webhook as mw  # noqa: E402
import worker_start_model as wsm  # noqa: E402


DOC = {
    "agents": [
        {"agent": "Grok", "cli": "Grok", "model": "grok-4.7", "context": "256000", "effort": "low"},
        {"agent": "Cursor", "cli": "Cursor", "model": "gpt-5", "context": "200000", "effort": ""},
    ]
}


class _Resp:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_cursor_dryrun_cites_webhook_model_not_tray(tmp_path, monkeypatch):
    mw.clear_models_webhook_cache()
    tray = tmp_path / "Bobiverse" / "tray-models.json"
    tray.parent.mkdir(parents=True)
    tray.write_text(
        json.dumps({"workerStartModels": {"cursor": "tray-cursor-model"}}),
        encoding="utf-8",
    )

    def fake_open(req, timeout=0):
        return _Resp(json.dumps(DOC).encode("utf-8"))

    monkeypatch.setattr(mw.urllib.request, "urlopen", fake_open)
    env = {
        "LOCALAPPDATA": str(tmp_path),
        "BOB_MODELS_WEBHOOK_URL": "http://127.0.0.1/models",
    }
    settings = wsm.resolved_start_settings("cursor", env=env)
    assert settings["model"] == "gpt-5"
    assert settings["settings_source"] == "webhook"
    assert settings["model"] != "tray-cursor-model"
    args = list(settings["cli_settings_args"])
    assert args == ["--model", "gpt-5"]
    log = tmp_path / "launch-dryrun.jsonl"
    wsm.append_launch_dryrun(
        {
            "kind": "cursor",
            "mode": "agent",
            "settings_source": settings["settings_source"],
            "model": settings["model"],
            "context": settings["context"],
            "effort": settings["effort"],
            "setting_status": settings["setting_status"],
            "cli_args": ["C:/fake/cursor.exe"] + args,
            "executable": "C:/fake/cursor.exe",
        },
        path=log,
        env=env,
    )
    line = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert line["kind"] == "cursor"
    assert line["settings_source"] == "webhook"
    assert "gpt-5" in line["cli_args"]
    assert "tray-cursor-model" not in line["cli_args"]
