"""Explicit tray/CLI agent choice. Automatic order stays Grok, then Cursor, then OpenCode."""
from __future__ import annotations

import json
from pathlib import Path

import bob.scripts.bob_worker as bw

CUR, GRK, OP = r"C:\c\agent.cmd", r"C:\g\agent.exe", r"C:\o\opencode.exe"


def _fuel(**kwargs):
    return bw.Fuel(**kwargs)


def test_automatic_still_prefers_grok_when_opencode_has_fuel():
    fuel = _fuel(grok_pct=99, grok_state="available", opencode_free=100)
    dec = bw.resolve_seat_decision("", bw.select_agent(fuel, CUR, GRK), fuel, CUR, GRK, OP, auth_present=True)
    assert dec.kind == "grok"


def test_explicit_opencode_starts_when_free_fuel_is_real():
    fuel = _fuel(grok_pct=99, grok_state="available", opencode_free=100, opencode_go=None)
    dec = bw.explicit_agent_decision("opencode", fuel, CUR, GRK, OP, auth_present=False)
    assert dec.kind == "opencode"
    assert "free=100" in dec.reason


def test_explicit_opencode_refuses_without_fuel_and_does_not_pick_grok():
    fuel = _fuel(grok_pct=99, grok_state="available")
    dec = bw.explicit_agent_decision("opencode", fuel, CUR, GRK, OP, auth_present=True)
    assert dec.kind == "refuse"
    assert dec.reason.startswith("explicit opencode: no usable fuel")


def test_explicit_opencode_refuses_when_command_missing():
    fuel = _fuel(opencode_free=100)
    dec = bw.explicit_agent_decision("opencode", fuel, CUR, GRK, None, auth_present=True)
    assert dec.kind == "refuse"
    assert "opencode.exe missing" in dec.reason


def test_explicit_opencode_go_only_needs_auth_file_not_a_token_read(tmp_path, monkeypatch):
    fuel = _fuel(opencode_go=40, opencode_free=0)
    missing = bw.explicit_agent_decision("opencode", fuel, CUR, GRK, OP, auth_present=False)
    assert missing.kind == "refuse"
    assert "auth.json absent" in missing.reason
    home = tmp_path / "profile"
    auth = home / ".local" / "share" / "opencode" / "auth.json"
    auth.parent.mkdir(parents=True)
    auth.write_text('{"not":"read"}', encoding="utf-8")
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("HOME", raising=False)
    assert bw.opencode_auth_file_present() is True
    assert auth.read_text(encoding="utf-8") == '{"not":"read"}'
    ready = bw.explicit_agent_decision(
        "opencode", fuel, CUR, GRK, OP, auth_present=bw.opencode_auth_file_present()
    )
    assert ready.kind == "opencode"


def test_explicit_grok_and_cursor_refuse_when_missing():
    fuel = _fuel(grok_pct=0, grok_state="exhausted", cursor_high=0, cursor_low=0, opencode_free=100)
    assert bw.explicit_agent_decision("grok", fuel, CUR, None, OP, auth_present=True).kind == "refuse"
    assert bw.explicit_agent_decision("cursor", fuel, None, GRK, OP, auth_present=True).kind == "refuse"
    assert bw.explicit_agent_decision("grok", fuel, CUR, GRK, OP, auth_present=True).reason.startswith(
        "explicit grok:"
    )


def test_list_agents_is_agents_not_fuel_pools():
    fuel = _fuel(grok_pct=99, grok_state="available", cursor_low=84, opencode_free=100)
    rows = bw.list_worker_agents(fuel, CUR, GRK, OP, auth_present=True)
    assert [r["id"] for r in rows] == ["auto", "grok", "cursor", "opencode"]
    assert rows[0]["available"] is True
    assert rows[1]["available"] is True and rows[1]["installed"] is True
    assert rows[3]["available"] is True
    assert "opencode-free" not in json.dumps(rows)
    bare = bw.list_worker_agents(_fuel(), None, None, None, auth_present=False)
    assert bare[1]["installed"] is False and bare[1]["available"] is False
    assert bare[3]["reason"].startswith("explicit opencode:")


def test_describe_launch_passes_explicit_agent_only_when_requested(tmp_path: Path):
    root = tmp_path / "bob"
    (root / "worker").mkdir(parents=True)
    (root / "worker" / "bob-worker.exe").write_bytes(b"MZ")
    local = tmp_path / "local"
    local.mkdir()
    auto = bw.describe_worker_exe_launch(str(root), "agent", "marchhare", local_app_data=str(local))
    assert "--agent" not in auto["argv"]
    assert auto["agent"] == ""
    picked = bw.describe_worker_exe_launch(
        str(root), "agent", "marchhare", local_app_data=str(local), agent="opencode"
    )
    assert picked["argv"][picked["argv"].index("--agent") + 1] == "opencode"
    assert picked["agent"] == "opencode"


def test_dry_run_explicit_opencode_refuses_instead_of_grok(monkeypatch, capsys, tmp_path: Path):
    monkeypatch.setattr(bw, "resolve_grok_exe", lambda *a, **k: GRK)
    monkeypatch.setattr(bw, "resolve_cursor_cmd", lambda *a, **k: CUR)
    monkeypatch.setattr(bw, "resolve_opencode_cmd", lambda *a, **k: OP)
    monkeypatch.setattr(bw, "read_fuel", lambda *a, **k: _fuel(grok_pct=99, grok_state="available"))
    monkeypatch.setattr(bw, "opencode_auth_file_present", lambda env=None: True)
    code = bw.main(["--dry-run", "--install-root", str(tmp_path), "--agent", "opencode"])
    assert code == bw.EXIT_OK
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["decision"] == "refuse"
    assert payload["agent"] == "opencode"
    assert payload["opencode_cmd"] is True


def test_list_agents_unknown_fuel_stays_clickable_and_does_not_read(monkeypatch, capsys, tmp_path: Path):
    calls = []
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(bw, "resolve_grok_exe", lambda *a, **k: GRK)
    monkeypatch.setattr(bw, "resolve_cursor_cmd", lambda *a, **k: CUR)
    monkeypatch.setattr(bw, "resolve_opencode_cmd", lambda *a, **k: OP)
    monkeypatch.setattr(bw, "read_fuel", lambda *a, **k: calls.append(1) or _fuel())
    monkeypatch.setattr(bw, "opencode_auth_file_present", lambda env=None: False)
    code = bw.main(["--list-agents", "--install-root", str(tmp_path)])
    assert code == bw.EXIT_OK
    assert calls == []
    listed = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert listed["refresh"] is True
    by_id = {row["id"]: row for row in listed["agents"]}
    assert by_id["auto"]["available"] is True
    for agent_id in ("grok", "cursor", "opencode"):
        assert by_id[agent_id]["available"] is True
        assert by_id[agent_id]["fuel_state"] == "unknown"
        assert "not exhausted" in by_id[agent_id]["reason"]
        assert "no usable fuel" not in by_id[agent_id]["reason"]


def test_refresh_fuel_uses_real_reading_then_cache(monkeypatch, capsys, tmp_path: Path):
    calls = []
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "Get-BobAgentFuel.ps1").write_text("x", encoding="utf-8")
    monkeypatch.setattr(bw, "resolve_grok_exe", lambda *a, **k: GRK)
    monkeypatch.setattr(bw, "resolve_cursor_cmd", lambda *a, **k: CUR)
    monkeypatch.setattr(bw, "resolve_opencode_cmd", lambda *a, **k: OP)
    monkeypatch.setattr(bw, "opencode_auth_file_present", lambda env=None: False)

    def read(install_root, run=None, timeout=90.0, provider=""):
        calls.append(provider)
        return _fuel(grok_pct=99, grok_state="available", opencode_free=100)

    monkeypatch.setattr(bw, "read_fuel", read)
    code = bw.main(["--list-agents", "--refresh-fuel", "--install-root", str(tmp_path)])
    assert code == bw.EXIT_OK
    assert set(calls) == {"cursor", "grok", "opencode"}
    listed = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert listed["refresh"] is False
    by_id = {row["id"]: row for row in listed["agents"]}
    assert by_id["opencode"]["available"] is True
    assert by_id["opencode"]["fuel_state"] == "known"
    calls.clear()
    code = bw.main(["--list-agents", "--install-root", str(tmp_path)])
    assert code == bw.EXIT_OK
    assert calls == []
    again = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert again["refresh"] is False
    assert {row["id"]: row["available"] for row in again["agents"]}["opencode"] is True


def test_known_exhausted_opencode_stays_unavailable_on_the_menu(monkeypatch, capsys, tmp_path: Path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(bw, "resolve_grok_exe", lambda *a, **k: GRK)
    monkeypatch.setattr(bw, "resolve_cursor_cmd", lambda *a, **k: CUR)
    monkeypatch.setattr(bw, "resolve_opencode_cmd", lambda *a, **k: OP)
    monkeypatch.setattr(bw, "opencode_auth_file_present", lambda env=None: True)
    assert bw.save_agent_list_fuel(_fuel(grok_pct=99, grok_state="available", opencode_free=0, opencode_go=0))
    code = bw.main(["--list-agents", "--install-root", str(tmp_path)])
    assert code == bw.EXIT_OK
    listed = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    by_id = {row["id"]: row for row in listed["agents"]}
    assert by_id["opencode"]["available"] is False
    assert by_id["opencode"]["reason"].startswith("explicit opencode: no usable fuel")
    assert listed["refresh"] is False


def test_slow_cursor_read_does_not_drop_opencode(tmp_path: Path):
    import subprocess
    import threading
    import time

    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "Get-BobAgentFuel.ps1").write_text("x", encoding="utf-8")
    state = {"n": 0, "max": 0}
    lock = threading.Lock()

    def run(cmd, timeout=8, **_k):
        provider = cmd[cmd.index("-Provider") + 1]
        with lock:
            state["n"] += 1
            state["max"] = max(state["max"], state["n"])
        try:
            time.sleep(0.2)
            if provider == "cursor":
                raise subprocess.TimeoutExpired(cmd, timeout)
            if provider == "opencode":
                stdout = '{"opencode":{"free":100,"go":null}}'
            else:
                stdout = '{"grok":{"remaining_pct":40,"state":"available"}}'

            class R:
                pass

            out = R()
            out.stdout = stdout
            return out
        finally:
            with lock:
                state["n"] -= 1

    fuel = bw.read_fuel_bounded(tmp_path, run=run, per_provider_s=2)
    assert state["max"] >= 2
    assert fuel.opencode_free == 100
    assert fuel.grok_pct == 40
    assert fuel.cursor_high is None


def test_unknown_agent_is_usage(capsys, tmp_path: Path):
    code = bw.main(["--dry-run", "--install-root", str(tmp_path), "--agent", "copilot"])
    assert code == bw.EXIT_USAGE
    err = capsys.readouterr().err
    assert "copilot" in err


def test_skill_start_it_agents_submenu_fr6220():
    """FR #6220: Start-it documents Agents submenu; no single-Agent / NO sub-menu claim."""
    skill = Path(__file__).resolve().parents[1] / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    assert "NO sub-menu" not in text
    assert "single menu item" not in text
    start = text.index("## Start it (three ways)")
    which = text.index("## Which agent starts")
    chunk = text[start:which]
    assert "**Tray: `Agents` submenu**" in chunk
    for name in ("Automatic", "Grok", "Cursor", "OpenCode"):
        assert name in chunk, name
    assert "--list-agents" in chunk
    assert "Plan** stays a separate top-level click" in chunk or "**Plan** stays a separate top-level click" in chunk
    assert "One tray **Agents** menu pick" in text
    assert "tray Agents submenu" in text.split("---", 2)[1]
