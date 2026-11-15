"""FR #7706: digest must not publish a PowerShell $model template or relabel OpenCode as grok."""
from __future__ import annotations

import bobreport
import registered_machines
import shop_listen
import worker_start_model as wsm


def test_script_model_template_is_not_a_model_id():
    text = "\n".join(
        [
            "$model = $env:BOB_OPENCODE_MODEL",
            "$record = & $py record-pause --dir $dir --model $model",
            "& $exe run -m $model $line",
        ]
    )
    assert wsm.concrete_model_id("$model") == ""
    assert wsm._model_from_script_text(text) == ""
    assert wsm._model_from_script_text(text + "\n--model opencode/deepseek-v4.1-flash-free") == (
        "opencode/deepseek-v4.1-flash-free"
    )


def test_activity_merge_keeps_opencode_kind(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"marchhare"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    doc = bobreport.empty_digest()
    doc["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    doc["machines"]["marchhare"]["workers"] = {
        "28996": {
            "pid": "28996",
            "nick": "marchhare-28996",
            "kind": "opencode",
            "state": "idle",
            "working_on": "",
            "start_model": "opencode/deepseek-v4.1-flash-free",
            "model": "opencode/deepseek-v4.1-flash-free",
        }
    }
    bobreport.save_digest(home, doc)
    payload = shop_listen.format_activity_payload(
        machine="marchhare",
        pid=28996,
        nick="marchhare-28996",
        kind="",
        working_on="FR SimonBarnett/bobiverse#7706",
        state="running",
    )
    assert "kind" not in payload
    bobreport.apply_callback(home, payload, "Jeeves")
    saved = bobreport.load_digest(home)
    row = saved["machines"]["marchhare"]["workers"]["28996"]
    assert row["kind"] == "opencode"
    assert row["start_model"] == "opencode/deepseek-v4.1-flash-free"
    assert "$" not in row["start_model"]
