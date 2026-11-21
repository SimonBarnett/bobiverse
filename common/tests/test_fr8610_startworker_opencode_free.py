"""FR #8610: !startworker accepts opencode / opencode free and queues agent+slot."""
from __future__ import annotations

import json
import os

import startworker as sw

NOW = 1_800_000_000.0
MID = lambda n: (n[4:].lower() if str(n).lower().startswith("bob-") else None)  # noqa: E731


def _q(tmp_path):
    d = sw.queue_dir(tmp_path / "bob")
    d.mkdir(parents=True)
    (d / sw.ALIVE_FILE).write_text("alive")
    os.utime(d / sw.ALIVE_FILE, (NOW, NOW))
    (d / sw.ENGINE_ALIVE_FILE).write_text("engine")
    os.utime(d / sw.ENGINE_ALIVE_FILE, (NOW, NOW))
    return d


def ask(q, body, **kw):
    args = dict(
        body=body,
        nick="Simon",
        account="simon",
        channel="#flamingo",
        local_machine="flamingo",
        gate=sw.StartGate(max_workers=4, cooldown_s=0),
        qdir=q,
        machine_of_nick=MID,
        procs=lambda: [],
        now=NOW,
    )
    args.update(kw)
    return sw.decide(**args)


def test_fr8610_parse_opencode_and_free_slot():
    assert sw.parse("!startworker opencode flamingo") == ("agent", "flamingo", "opencode", "")
    assert sw.parse("!startworker opencode free flamingo") == (
        "agent",
        "flamingo",
        "opencode",
        "free",
    )
    assert sw.parse("!startworker flamingo opencode paid") == (
        "agent",
        "flamingo",
        "opencode",
        "paid",
    )
    assert sw.parse("!startworker grok flamingo") == ("agent", "flamingo", "grok", "")
    assert sw.parse("!startworker agent flamingo") == ("agent", "flamingo", "", "")
    assert sw.parse("!startworker free flamingo") == "usage"  # free alone needs opencode
    assert sw.parse("!startworker plan opencode flamingo") == "usage"  # plan has no agent pin


def test_fr8610_queues_agent_opencode_and_slot(tmp_path, monkeypatch):
    monkeypatch.setattr(sw, "count_irc_agent_seats", lambda **kw: 0)
    q = _q(tmp_path)
    d = ask(q, "!startworker opencode free flamingo")
    assert d.ok, d.line
    assert "opencode" in d.line.lower()
    reqs = list(q.glob("req-*.json"))
    assert len(reqs) == 1
    body = json.loads(reqs[0].read_text(encoding="utf-8"))
    assert body["mode"] == "agent"
    assert body["agent"] == "opencode"
    assert body["slot"] == "free"


def test_fr8610_opencode_without_slot_omits_slot_key(tmp_path, monkeypatch):
    monkeypatch.setattr(sw, "count_irc_agent_seats", lambda **kw: 0)
    q = _q(tmp_path)
    assert ask(q, "!startworker opencode flamingo").ok
    body = json.loads(next(q.glob("req-*.json")).read_text(encoding="utf-8"))
    assert body["agent"] == "opencode"
    assert "slot" not in body


def test_fr8610_tray_launch_passes_model_for_slot():
    """Source pin: queue consumer must pass Model into Start-BobTrayWorkerExe."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    ps1 = (root / "bob" / "tray" / "tools" / "BobTrayStartWorker.ps1").read_text(encoding="utf-8")
    watch = (root / "bob" / "tray" / "tools" / "Watch-BobTray.ps1").read_text(encoding="utf-8")
    assert "function Resolve-BobTrayOpencodeSlotModel" in ps1
    assert "$Launch $mode $agent $model" in ps1
    assert "param($mode, $agent, $model)" in watch
    assert "-Model $model" in watch
    # Paid fallback must match tray default.json models.opencodePaid (FR #6429).
    assert "opencode-go/deepseek-v4-pro" in ps1
    assert "opencode/claude-sonnet-4" not in ps1
    cfg = (root / "bob" / "tray" / "config" / "default.json").read_text(encoding="utf-8")
    assert "opencode-go/deepseek-v4-pro" in cfg
