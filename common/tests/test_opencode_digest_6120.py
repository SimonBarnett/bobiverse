"""Digest / webhook tests for OpenCode fuel ids (issue #6120)."""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest import mock

import bobreport


def test_pcent_retains_opencode_fuel_ids(tmp_path: Path):
    raw = {
        "online": True,
        "pcent": {
            "cursor-models": 40,
            "opencode-free": 100,
            "opencode-go": 50,
        },
    }
    ent = bobreport._coerce_machine("marchhare", raw)
    assert ent["pcent"]["opencode-free"] == 100
    assert ent["pcent"]["opencode-go"] == 50


def test_export_machine_for_tray_keeps_opencode_pcent(tmp_path: Path):
    home = tmp_path / "digest"
    home.mkdir()
    doc = bobreport.empty_digest()
    doc["machines"]["marchhare"] = {
        "online": True,
        "pcent": {"opencode-free": 100, "opencode-go": 50},
    }
    bobreport.save_digest(home, doc)
    exported = bobreport.export_machine_for_tray(home, "marchhare", doc["machines"]["marchhare"])
    assert exported["pcent"]["opencode-free"] == 100
    assert exported["pcent"]["opencode-go"] == 50


# --- FR #6146: ear publish includes OpenCode pcent when known ---

FIXTURE_FREE100_GO50 = '{"costs": {"glm-5.3": 7.5}, "free_models": ["beam-free"]}'


def test_fr6146_read_local_opencode_pcent_from_fixture(monkeypatch):
    bobreport.clear_opencode_pcent_cache()
    monkeypatch.delenv("BOB_OPENCODE_GO_USAGE_FIXTURE", raising=False)
    monkeypatch.setenv("BOB_OPENCODE_FUEL_FIXTURE", FIXTURE_FREE100_GO50)
    monkeypatch.delenv("BOB_OPENCODE_FUEL_HELPER", raising=False)
    got = bobreport.read_local_opencode_pcent()
    assert got.get("opencode-free") == 100
    assert got.get("opencode-go") == 50
    # Never invent unknown keys as 0
    assert "opencode-free" in got and "opencode-go" in got


def test_fr6146_read_local_opencode_pcent_unknown_omits(monkeypatch):
    bobreport.clear_opencode_pcent_cache()
    _isolate_live_opencode_key(monkeypatch)
    # Force helper miss so live CLI is not required
    monkeypatch.setenv("BOB_OPENCODE_FUEL_HELPER", str(Path("C:/no/such/Get-BobOpencodeFuel.ps1")))
    got = bobreport.read_local_opencode_pcent()
    assert got == {}
    assert "opencode-free" not in got
    assert "opencode-go" not in got


def test_fr6146_enrich_peer_merges_known_only():
    peer = {"id": "redqueen", "pcent": {"grok-chat": 42}}
    enriched = bobreport.enrich_peer_with_opencode_pcent(
        peer, {"opencode-free": 100, "opencode-go": 50}
    )
    assert enriched["pcent"]["grok-chat"] == 42
    assert enriched["pcent"]["opencode-free"] == 100
    assert enriched["pcent"]["opencode-go"] == 50
    # empty/unknown: no invent
    peer2 = {"id": "redqueen", "pcent": {"grok-chat": 42}}
    enriched2 = bobreport.enrich_peer_with_opencode_pcent(peer2, {})
    assert "opencode-free" not in enriched2["pcent"]
    assert "opencode-go" not in enriched2["pcent"]
    # None values omitted; explicit 0 (exhausted) kept
    peer3 = {"id": "redqueen", "pcent": {}}
    enriched3 = bobreport.enrich_peer_with_opencode_pcent(
        peer3, {"opencode-free": None, "opencode-go": 0}
    )
    assert "opencode-free" not in enriched3["pcent"]
    assert enriched3["pcent"]["opencode-go"] == 0


def test_fr6146_publish_round_trip_fixture(tmp_path: Path, monkeypatch):
    """Fixture free=100 go=50 -> merge payload pcent keys match (FR #6146)."""
    import json
    from unittest import mock

    import bobstat

    monkeypatch.delenv("BOB_OPENCODE_GO_USAGE_FIXTURE", raising=False)
    monkeypatch.setenv("BOB_OPENCODE_FUEL_FIXTURE", FIXTURE_FREE100_GO50)
    home = tmp_path / "home"
    home.mkdir()
    mid = "redqueen"
    peer = {
        "ok": True,
        "id": mid,
        "online": True,
        "status": "operational",
        "weekly": 80,
        "weekly_known": True,
        "pcent": {"grok-chat": 42},
        "lastSeen": "2026-11-07T12:00:00Z",
    }
    bobstat.write_peer(home, peer)
    posted: list[dict] = []

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        posted.append(json.loads(req.data.decode("utf-8")))

        class Resp:
            status = 204

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b""

        return Resp()

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        code = bobreport.publish_local_peer_fuel(
            home, mid, force=True, url="https://example.test/bob/v1/report"
        )
    assert code == 204
    assert len(posted) == 1
    body = posted[0]
    assert body.get("op") == "merge"
    assert body["pcent"]["opencode-free"] == 100
    assert body["pcent"]["opencode-go"] == 50
    assert body["pcent"]["grok-chat"] == 42
    blob = json.dumps(body)
    assert not bobreport.looks_like_secret(blob)


def test_fr6146_publish_omits_opencode_when_unknown(tmp_path: Path, monkeypatch):
    import json
    from unittest import mock

    import bobstat

    _isolate_live_opencode_key(monkeypatch)
    monkeypatch.setenv("BOB_OPENCODE_FUEL_HELPER", str(Path("C:/no/such/Get-BobOpencodeFuel.ps1")))
    home = tmp_path / "home"
    home.mkdir()
    mid = "redqueen"
    peer = {
        "ok": True,
        "id": mid,
        "online": True,
        "status": "operational",
        "weekly": 80,
        "weekly_known": True,
        "pcent": {"grok-chat": 42},
        "lastSeen": "2026-11-07T12:00:00Z",
    }
    bobstat.write_peer(home, peer)
    posted: list[dict] = []

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        posted.append(json.loads(req.data.decode("utf-8")))

        class Resp:
            status = 204

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b""

        return Resp()

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        code = bobreport.publish_local_peer_fuel(
            home, mid, force=True, url="https://example.test/bob/v1/report"
        )
    assert code == 204
    body = posted[0]
    pcent = body.get("pcent") or {}
    assert "opencode-free" not in pcent
    assert "opencode-go" not in pcent
    assert pcent.get("grok-chat") == 42


# --- MRB #6176 hostile: helper TTL cache + short timeout (CodeRabbit Major) ---


def test_mrb6176_helper_timeout_default_is_short():
    assert bobreport.DEFAULT_OPENCODE_FUEL_HELPER_TIMEOUT_S <= 5.0
    assert bobreport.DEFAULT_OPENCODE_FUEL_CACHE_S >= 5.0
    # Source must not use the old 45s helper timeout on the ear tick path.
    src = Path(bobreport.__file__).read_text(encoding="utf-8")
    assert "timeout=45" not in src
    assert "DEFAULT_OPENCODE_FUEL_HELPER_TIMEOUT_S" in src
    assert "_opencode_pcent_cache" in src


def _popen_writer(payload: str, *, running: bool = False):
    """Popen stand-in. A running child does not write; a finished one does."""

    class Proc:
        def __init__(self):
            self.returncode = None if running else 0
            self.killed = False

        def poll(self):
            if self.killed:
                self.returncode = -9
                return -9
            if running:
                return None
            self.returncode = 0
            return 0

        def kill(self):
            self.killed = True

    def fake_popen(argv, **kwargs):  # noqa: ARG001
        fh = kwargs.get("stdout")
        if fh is not None and not running:
            fh.write(payload)
            fh.flush()
        return Proc()

    return fake_popen


def _isolate_live_opencode_key(monkeypatch) -> None:
    """FR #7072 / #7067: !build as LocalSystem still loads seat auth.json / zen env.

    Helper-path pins must not take GO_USAGE_FIXTURE, FUEL_FIXTURE, or a live Go key.
    """
    for key in (
        "BOB_OPENCODE_GO_API_KEY",
        "BOB_OPENCODE_GO_USAGE_FIXTURE",
        "BOB_OPENCODE_FUEL_FIXTURE",
        "BOB_OPENCODE_WINDOWS_FIXTURE",
        "BOB_OPENCODE_AUTH_PATH",
        "BOB_OPENCODE_SEAT_HOME",
        "BOB_OPENCODE_KEY_LABEL",
        "BOB_GROK_WEEKLY_USER_HOME",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(bobreport, "_is_local_system_process", lambda: False)
    monkeypatch.setattr(bobreport, "_interactive_grok_user_home", lambda: None)
    monkeypatch.setattr(
        bobreport, "load_opencode_go_key_from_auth", lambda path: ("", "test-isolated")
    )


def _hermetic_opencode_helper_env(monkeypatch, tmp_path: Path) -> Path:
    """Isolate helper reads from install-root disk cache and Go-zen / fixture keys.

    FR #6710: release runners with a prior ``run/opencode-fuel.json`` (or a live
    Go key) made ``publish_local_peer_fuel`` re-publish cached free/go even when
    the stub helper returned ``opencode_missing`` nulls.
    FR #7072: also stub auth.json so LocalSystem does not skip the helper.
    """
    bobreport.clear_opencode_pcent_cache()
    _isolate_live_opencode_key(monkeypatch)
    helper = tmp_path / "Get-BobOpencodeFuel.ps1"
    helper.write_text("# stub\n", encoding="utf-8")
    cache = tmp_path / "opencode-fuel.json"
    monkeypatch.setenv("BOB_OPENCODE_FUEL_HELPER", str(helper))
    monkeypatch.setenv("BOB_OPENCODE_FUEL_CACHE_FILE", str(cache))
    return helper


def test_mrb6176_helper_cache_avoids_repeat_subprocess(monkeypatch, tmp_path: Path):
    """Within TTL, second read must not spawn PowerShell again."""
    from unittest import mock

    _hermetic_opencode_helper_env(monkeypatch, tmp_path)
    helper = tmp_path / "Get-BobOpencodeFuel.ps1"
    helper.write_text("# stub\n", encoding="utf-8")
    monkeypatch.setenv("BOB_OPENCODE_FUEL_HELPER", str(helper))
    monkeypatch.setenv("BOB_OPENCODE_FUEL_CACHE_S", "30")
    calls: list[int] = []

    def fake_popen(argv, **kwargs):
        calls.append(1)
        return _popen_writer('{"free": 80, "go": 40}\n')(argv, **kwargs)

    with mock.patch("subprocess.Popen", fake_popen):
        a = bobreport.read_local_opencode_pcent(now=1000.0)
        b = bobreport.read_local_opencode_pcent(now=1010.0)  # within 30s TTL
    assert a == {"opencode-free": 80, "opencode-go": 40}
    assert b == a
    assert len(calls) == 1


def test_mrb6176_helper_timeout_returns_stale_cache(monkeypatch, tmp_path: Path):
    """A still-running helper must not wipe the last good reading or block."""
    from unittest import mock

    _hermetic_opencode_helper_env(monkeypatch, tmp_path)
    helper = tmp_path / "Get-BobOpencodeFuel.ps1"
    helper.write_text("# stub\n", encoding="utf-8")
    monkeypatch.setenv("BOB_OPENCODE_FUEL_HELPER", str(helper))
    monkeypatch.setenv("BOB_OPENCODE_FUEL_CACHE_S", "30")
    n = {"i": 0}

    def fake_popen(argv, **kwargs):
        n["i"] += 1
        running = n["i"] > 1
        return _popen_writer(
            '{"free": 70, "go": 20}\n', running=running
        )(argv, **kwargs)

    with mock.patch("subprocess.Popen", fake_popen):
        first = bobreport.read_local_opencode_pcent(now=2000.0, force=True)
        # TTL elapsed, refresh starts a helper that is still inside opencode stats.
        second = bobreport.read_local_opencode_pcent(now=2040.0, force=True)
        # Still in flight: no third spawn, last numbers kept.
        third = bobreport.read_local_opencode_pcent(now=2045.0, force=True)
    assert first == {"opencode-free": 70, "opencode-go": 20}
    assert second == first
    assert third == first
    assert n["i"] == 2
    bobreport.clear_opencode_pcent_cache()


# MarchHare tray-status.json after the 10fe0381 install: helper killed before JSON.
_NULL_HELPER_JSON = (
    '{"free": null, "go": null, "windows": {"rolling": {"status": "unknown"},'
    ' "week": {"status": "unknown"}, "month": {"status": "unknown"}},'
    ' "read_state": "opencode_missing", "limiting": null}\n'
)
_LATER_HELPER_JSON = (
    '{"free": null, "go": 28, "windows": {'
    '"rolling": {"status": "unknown"},'
    '"week": {"status": "known", "used_pct": 72, "remaining_pct": 28, "reset_label": "1d 2h"},'
    '"month": {"status": "known", "used_pct": 36, "remaining_pct": 64, "reset_label": "26d 18h"}'
    '}, "read_state": "ok", "limiting": "week"}\n'
)


def test_accept_opencode_missing_keeps_windows_drops_cached_free():
    """FR #6710: opencode_missing null free/go must not re-publish prior free/go."""
    cached = {
        "free": 70,
        "go": 20,
        "opencode-free": 70,
        "opencode-go": 20,
        "read_state": "ok",
        "windows": {
            "rolling": {"status": "unknown"},
            "week": {"status": "known", "remaining_pct": 28},
            "month": {"status": "known", "remaining_pct": 64},
        },
    }
    # Parser drops null free/go — fresh looks like helper stdout after parse.
    fresh = bobreport._parse_opencode_helper_stdout(_NULL_HELPER_JSON)
    assert "opencode-free" not in fresh and fresh.get("read_state") == "opencode_missing"
    got = bobreport._accept_opencode_fuel_doc(fresh, cached)
    assert "free" not in got and "opencode-free" not in got
    assert "go" not in got and "opencode-go" not in got
    assert got["windows"]["week"]["remaining_pct"] == 28
    assert got["read_state"] == "opencode_missing"


def test_slow_helper_does_not_block_and_later_tick_keeps_windows(monkeypatch, tmp_path: Path):
    """Live opencode outlives the old 5s kill. The next tick must see its JSON."""
    from unittest import mock

    _hermetic_opencode_helper_env(monkeypatch, tmp_path)
    monkeypatch.setenv("BOB_OPENCODE_FUEL_CACHE_S", "0")
    phase = {"running": True}

    def fake_popen(argv, **kwargs):
        class Proc:
            def poll(self):
                if phase["running"]:
                    return None
                path = bobreport._opencode_fuel_cache.get("stdout_path")
                if isinstance(path, str) and path:
                    Path(path).write_text(_LATER_HELPER_JSON, encoding="utf-8")
                return 0

            def kill(self):
                phase["running"] = False

        return Proc()

    with mock.patch("subprocess.Popen", fake_popen):
        started = time.perf_counter()
        first = bobreport.read_local_opencode_fuel_doc(now=3000.0, force=True)
        elapsed = time.perf_counter() - started
        assert elapsed < 1.0
        assert first == {}
        phase["running"] = False
        second = bobreport.read_local_opencode_fuel_doc(now=3005.0, force=True)
    assert "opencode-free" not in second
    assert second.get("opencode-go") == 28
    wins = second["windows"]
    assert wins["rolling"]["status"] == "unknown"
    assert wins["week"]["remaining_pct"] == 28
    assert wins["week"]["reset_label"] == "1d 2h"
    assert wins["month"]["remaining_pct"] == 64
    bobreport.clear_opencode_pcent_cache()


def test_missing_upstream_publishes_windows_without_inventing_free(
    tmp_path: Path, monkeypatch
):
    """Null helper JSON still publishes three Go windows and does not set free=100."""
    import bobstat

    _hermetic_opencode_helper_env(monkeypatch, tmp_path)
    # Prior disk cache with free/go must not leak into this publish (FR #6710).
    cache = tmp_path / "opencode-fuel.json"
    cache.write_text(
        json.dumps({"free": 70, "go": 20, "read_state": "ok"}) + "\n", encoding="utf-8"
    )
    home = tmp_path / "home"
    home.mkdir()
    bobstat.write_peer(
        home,
        {
            "ok": True,
            "id": "marchhare",
            "online": True,
            "status": "operational",
            "weekly": 80,
            "weekly_known": True,
            "pcent": {"grok-chat": 42},
            "lastSeen": "2026-11-08T11:59:00Z",
        },
    )
    posted: list[dict] = []

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        posted.append(json.loads(req.data.decode("utf-8")))

        class Resp:
            status = 204

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b""

        return Resp()

    with mock.patch("subprocess.Popen", _popen_writer(_NULL_HELPER_JSON)):
        with mock.patch("urllib.request.urlopen", fake_urlopen):
            with mock.patch("bobreport.fetch_live_xai_weekly", return_value=None):
                code = bobreport.publish_local_peer_fuel(
                    home, "marchhare", force=True, url="https://example.test/bob/v1/report"
                )
    assert code == 204
    body = posted[0]
    pcent = body.get("pcent") or {}
    assert "opencode-free" not in pcent
    assert "opencode-go" not in pcent
    assert pcent.get("grok-chat") == 42
    wins = body["opencode_windows"]
    assert wins["rolling"]["status"] == "unknown"
    assert wins["week"]["status"] == "unknown"
    assert wins["month"]["status"] == "unknown"
    assert wins["rolling"].get("remaining_pct") is None
    bobreport.clear_opencode_pcent_cache()


def test_disk_cache_survives_restart_and_failed_reread_does_not_wipe(
    tmp_path: Path, monkeypatch
):
    """Tray and ear share run/opencode-fuel.json. A later opencode_missing must not erase week."""
    _hermetic_opencode_helper_env(monkeypatch, tmp_path)
    cache = tmp_path / "run" / "opencode-fuel.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("BOB_OPENCODE_FUEL_CACHE_FILE", str(cache))
    monkeypatch.setenv("BOB_OPENCODE_FUEL_CACHE_S", "0")
    helper = tmp_path / "Get-BobOpencodeFuel.ps1"

    with mock.patch("subprocess.Popen", _popen_writer(_LATER_HELPER_JSON)):
        first = bobreport.read_local_opencode_fuel_doc(now=4000.0, force=True)
    assert first["windows"]["week"]["remaining_pct"] == 28
    assert cache.is_file()
    bobreport.clear_opencode_pcent_cache()
    phase = {"running": True}

    def hanging(argv, **kwargs):  # noqa: ARG001
        class Proc:
            def poll(self):
                return None if phase["running"] else 0

            def kill(self):
                phase["running"] = False

        return Proc()

    with mock.patch("subprocess.Popen", hanging):
        during = bobreport.read_local_opencode_fuel_doc(now=5000.0, force=True)
    assert during["windows"]["week"]["remaining_pct"] == 28
    bobreport.clear_opencode_pcent_cache()
    with mock.patch("subprocess.Popen", _popen_writer(_NULL_HELPER_JSON)):
        failed = bobreport.read_local_opencode_fuel_doc(now=6000.0, force=True)
    assert failed["windows"]["week"]["remaining_pct"] == 28
    assert "opencode-free" not in failed
    bobreport.clear_opencode_pcent_cache()

