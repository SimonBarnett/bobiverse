"""FR #7366: fleet OpenCode/Copilot live only on digest.fleet_pools, never machines.*."""
from __future__ import annotations

import json
from pathlib import Path

import bobreport


def _roster(home: Path) -> None:
    (home / "registered-machines.json").write_text(
        json.dumps({"v": 1, "machines": ["marchhare"]}),
        encoding="utf-8",
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None


def test_fr7366_machine_post_opencode_windows_not_exported(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    doc = {"v": 1, "machines": {}, "fleet_pools": {
        "opencode-go": {"remaining": 71, "fetched_at": "2026-11-14T21:00:00Z"},
        "copilot": {"remaining": 40, "fetched_at": "2026-11-14T21:00:00Z"},
    }}
    bobreport._apply_merge_payload(
        doc,
        "marchhare",
        {
            "op": "merge",
            "machine": "marchhare",
            "online": True,
            "pcent": {"opencode-go": 28, "grok-chat": 74},
            "opencode_windows": {"week": {"remaining_pct": 28, "fetched_at": "2026-11-14T17:50:00Z"}},
            "copilot": {"remaining": 1, "fetched_at": ""},
        },
    )
    ent = doc["machines"]["marchhare"]
    assert "opencode_windows" not in ent
    assert "copilot" not in ent
    assert "opencode-go" not in (ent.get("pcent") or {})
    assert (ent.get("pcent") or {}).get("grok-chat") == 74
    bobreport.save_digest(tmp_path, doc)
    pub = bobreport.build_digest_object(tmp_path, "Jeeves")
    machine = (pub.get("machines") or {}).get("marchhare") or {}
    assert "opencode_windows" not in machine
    assert "copilot" not in machine
    assert "opencode-go" not in (machine.get("pcent") or {})
    assert (pub.get("fleet_pools") or {}).get("opencode-go", {}).get("remaining") == 71
    assert (pub.get("fleet_pools") or {}).get("copilot", {}).get("remaining") == 40


def test_fr7366_digest_copilot_ignores_stale_machine_copy(tmp_path: Path, monkeypatch):
    home = tmp_path / "d"
    home.mkdir()
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    _roster(home)
    doc = {
        "v": 1,
        "machines": {
            "marchhare": {
                "id": "marchhare",
                "copilot": {"remaining": 3, "fetched_at": ""},
            }
        },
        "copilot": {
            "remaining": 40,
            "fetched_at": "2026-11-14T21:00:00Z",
            "state": "ok",
            "source": "copilot_internal/user",
        },
        "fleet_pools": {
            "copilot": {
                "remaining": 40,
                "fetched_at": "2026-11-14T21:00:00Z",
                "state": "ok",
                "source": "copilot_internal/user",
            }
        },
    }
    bobreport.save_digest(home, doc)
    pub = bobreport.build_digest_object(home, "Jeeves")
    assert pub["copilot"]["remaining"] == 40
    assert pub["copilot"]["fetched_at"] == "2026-11-14T21:00:00Z"
    assert "copilot" not in ((pub.get("machines") or {}).get("marchhare") or {})


def test_fr7366_tray_hover_skips_machine_opencode_fallback():
    hover = Path(__file__).resolve().parents[2] / "bob" / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
    text = hover.read_text(encoding="utf-8")
    fn = text[text.index("function Get-BobOpencodePaintFromDigest") :]
    fn = fn[: fn.index("function ", 20)]
    assert "FR #7366" in fn
    assert "$ent.opencode_windows" not in fn
    assert "$pc.'opencode-go'" not in fn
