import json, threading, os
from pathlib import Path
import pytest
import bobreport
import registered_machines


@pytest.fixture()
def home(tmp_path):
    registered_machines.save_registered(tmp_path, {"flamingo", "win-mpre8vi4u6u"})
    return tmp_path


def test_save_digest_uses_unique_tmp_and_leaves_none(home, monkeypatch):
    seen = []
    real = bobreport._replace_with_retry

    def spy(src, dst):
        seen.append(Path(src).name)
        return real(src, dst)

    monkeypatch.setattr(bobreport, "_replace_with_retry", spy)
    bobreport.save_digest(home, bobreport.load_digest(home))
    bobreport.save_digest(home, bobreport.load_digest(home))
    assert len(set(seen)) == 2
    assert all(n != "digest.json.tmp" and n.endswith(".tmp") for n in seen)
    assert not list(home.glob("*.tmp"))


def test_replace_retries_on_winerror_32_then_succeeds(tmp_path, monkeypatch):
    """FR #35 / #51: report route failed with WinError 32 on digest.json.tmp -> digest.json."""
    src = tmp_path / "a.tmp"; dst = tmp_path / "a"
    src.write_text("x")
    calls = {"n": 0}
    real = os.replace

    def flaky(s, d):
        calls["n"] += 1
        if calls["n"] < 3:
            e = PermissionError(13, "sharing violation"); e.winerror = 32
            raise e
        return real(s, d)

    monkeypatch.setattr(bobreport.os, "replace", flaky)
    monkeypatch.setattr(bobreport, "_REPLACE_RETRY_DELAYS", (0.0, 0.0, 0.0, 0.0))
    bobreport._replace_with_retry(src, dst)
    assert calls["n"] == 3 and dst.read_text() == "x"


def test_replace_retries_on_winerror_5(tmp_path, monkeypatch):
    """Sibling intake #38: WinError 5 access denied on the same replace."""
    src = tmp_path / "a.tmp"; dst = tmp_path / "a"
    src.write_text("x")
    calls = {"n": 0}
    real = os.replace

    def flaky(s, d):
        calls["n"] += 1
        if calls["n"] < 2:
            e = PermissionError(13, "access denied"); e.winerror = 5
            raise e
        return real(s, d)

    monkeypatch.setattr(bobreport.os, "replace", flaky)
    monkeypatch.setattr(bobreport, "_REPLACE_RETRY_DELAYS", (0.0, 0.0, 0.0))
    bobreport._replace_with_retry(src, dst)
    assert calls["n"] == 2 and dst.read_text() == "x"


def test_save_digest_retries_tmp_write_on_sharing_error(home, monkeypatch):
    """Sibling intake #37: PermissionError on writing digest.json*.tmp before replace."""
    calls = {"n": 0}
    real_write = Path.write_text

    def flaky(self, *args, **kwargs):
        if self.name.startswith("digest.json.") and self.suffix == ".tmp":
            calls["n"] += 1
            if calls["n"] < 3:
                e = PermissionError(13, "permission denied"); e.winerror = 32
                raise e
        return real_write(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", flaky)
    monkeypatch.setattr(bobreport, "_REPLACE_RETRY_DELAYS", (0.0, 0.0, 0.0, 0.0))
    bobreport.save_digest(home, bobreport.load_digest(home))
    assert calls["n"] == 3
    assert bobreport.digest_path(home).is_file()
    assert not list(home.glob("digest.json*.tmp"))


def test_replace_gives_up_after_retries_and_non_sharing_errors_raise_at_once(tmp_path, monkeypatch):
    src = tmp_path / "a.tmp"; src.write_text("x")
    n = {"c": 0}

    def always(s, d):
        n["c"] += 1
        raise PermissionError(13, "denied")

    monkeypatch.setattr(bobreport.os, "replace", always)
    monkeypatch.setattr(bobreport, "_REPLACE_RETRY_DELAYS", (0.0, 0.0))
    with pytest.raises(PermissionError):
        bobreport._replace_with_retry(src, tmp_path / "a")
    assert n["c"] == 3

    n["c"] = 0

    def missing(s, d):
        n["c"] += 1
        raise FileNotFoundError(2, "gone")

    monkeypatch.setattr(bobreport.os, "replace", missing)
    with pytest.raises(FileNotFoundError):
        bobreport._replace_with_retry(src, tmp_path / "a")
    assert n["c"] == 1


def test_stale_tmp_cleanup_removes_old_keeps_fresh(home):
    path = bobreport.digest_path(home)
    old = home / "digest.json.123.aaa.tmp"; old.write_text("{}")
    legacy = home / "digest.json.tmp"; legacy.write_text("{}")
    fresh = home / "digest.json.456.bbb.tmp"; fresh.write_text("{}")
    other = home / "queue.json.tmp"; other.write_text("{}")
    past = old.stat().st_mtime - 3600
    os.utime(old, (past, past)); os.utime(legacy, (past, past))
    assert bobreport._cleanup_stale_digest_tmp(path) == 2
    assert not old.exists() and not legacy.exists()
    assert fresh.exists() and other.exists()


def test_concurrent_merges_no_failures_no_lost_updates(home):
    errors = []
    n_threads, per = 8, 12

    def worker(i):
        try:
            for k in range(per):
                out = bobreport.apply_callback(home, {
                    "op": "merge", "machine": "flamingo", "pid": 1000 + i * 100 + k,
                    "working_on": f"t{i}-{k}", "kind": "grok"}, "Jeeves")
                if not out.ok:
                    errors.append(out.err)
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert errors == []
    doc = json.loads(bobreport.digest_path(home).read_text(encoding="utf-8"))
    workers = doc["machines"]["flamingo"]["workers"]
    assert len(workers) == n_threads * per          # no lost update
    assert not list(home.glob("digest.json.*.tmp"))


def test_digest_lock_is_reentrant(home):
    with bobreport.digest_lock(home):
        with bobreport.digest_lock(home):
            bobreport.persist_chair_nick(home, "Jeeves")
    assert bobreport.load_digest(home)["chairNick"] == "Jeeves"
