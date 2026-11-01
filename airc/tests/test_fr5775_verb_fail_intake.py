"""FR #5775: shared airc verb fail-intake wrapper, key, spool, entrypoint coverage."""
from __future__ import annotations

import json
from pathlib import Path

import airc_fail_intake as fi
import airc_console as ac


def test_fr5775_dedupe_key_shape():
    key = fi.dedupe_key(
        verb="legion",
        machine="flamingo",
        version="1.0.7",
        exc_class="RuntimeError",
    )
    assert key == "airc-legion-fail|flamingo|legion|1.0.7|runtimeerror"
    # Same inputs => same key (deterministic across Python/PS).
    assert key == fi.dedupe_key(
        verb="legion",
        machine="flamingo",
        version="1.0.7",
        exc_class="RuntimeError",
    )


def test_fr5775_report_redacts_secrets_and_posts(monkeypatch):
    posts: list[dict] = []

    def fake_post(title, body, *, repo, sig, exe):
        posts.append({"title": title, "body": body, "sig": sig, "repo": repo, "exe": exe})
        return {"ok": True, "number": 1}

    # filer_post bypasses FR #5783 pytest skip so intentional proofs still post.
    out = fi.report_verb_failure(
        "network",
        RuntimeError("boom password=FAKE_SECRET_VALUE user=DOMAIN\\admin"),
        args={"host": "walrus", "password": "FAKE_SECRET_VALUE"},
        version="1.0.7",
        machine="marchhare",
        wait_s=0,
        filer_post=fake_post,
    )
    assert out.get("ok") is True
    assert posts, "must post via native intake (packaged-safe)"
    blob = posts[0]["body"] + posts[0]["title"]
    assert "FAKE_SECRET_VALUE" not in blob
    assert "password=<redacted>" in blob.lower() or "<redacted>" in blob.lower()
    assert posts[0]["sig"].startswith("airc-network-fail|")
    assert "runtimeerror" in posts[0]["sig"]


def test_fr5775_spool_when_intake_down(tmp_path, monkeypatch):
    spool = tmp_path / "spool"
    monkeypatch.setenv("BOB_CRASH_SPOOL", str(spool))

    def boom(*_a, **_k):
        raise OSError("intake-unreachable")

    # Force intake_allowed so FR #5783 pytest skip does not hide the spool path.
    monkeypatch.setattr(fi, "intake_allowed", lambda **_k: True)
    monkeypatch.setattr(fi, "_native_post", boom)
    out = fi.report_verb_failure(
        "extension",
        ValueError("gpo failed"),
        args={"form": "CUSTOMERS"},
        version="1.0.7",
        machine="ionos",
        wait_s=0,
    )
    assert out.get("ok") is False
    assert out.get("spooled")
    files = list(spool.glob("*.json"))
    assert files, "must spool when intake unreachable"
    row = json.loads(files[0].read_text(encoding="utf-8"))
    assert "airc-extension-fail|" in str(row.get("sig") or "")
    assert "CUSTOMERS" in str(row.get("body") or "")


def test_fr5775_wrap_returns_failure_and_reports(monkeypatch):
    seen: list[str] = []

    def fake_report(verb, exc, **kw):
        seen.append(f"{verb}:{type(exc).__name__}")
        return {"ok": True, "dedupe_key": "x"}

    monkeypatch.setattr(fi, "report_verb_failure", fake_report)

    @fi.wrap_verb("legion")
    def blow(**_kw):
        raise RuntimeError("inject-fault")

    result = blow(target="flamingo")
    assert seen == ["legion:RuntimeError"]
    assert isinstance(result, dict)
    assert result.get("ok") is False
    assert result.get("error") == "RuntimeError"
    assert "inject-fault" in str(result.get("detail") or "")


def test_fr5775_every_registered_verb_is_wrapped():
    """Enumerate registered verbs; fail if any lacks wrap registration."""
    # Import production modules so @wrap_verb / mark_wrapped side-effects land.
    import airc_console  # noqa: F401
    import airc_legion  # noqa: F401
    import airc_extension  # noqa: F401
    import airc_network  # noqa: F401
    import airc_console_service  # noqa: F401
    import airc_isolated  # noqa: F401

    missing = sorted(fi.VERB_ENTRYPOINTS - fi.wrapped_verbs())
    assert not missing, f"unwrapped verbs: {missing}"
    # Core IRC verbs must be listed.
    for v in (
        "update",
        "version",
        "status",
        "legion",
        "extension",
        "network",
        "priority",
        "shell",
        "cred",
        "on_line",
        "handle",
        "installer_legion_work",
        "extension_gpo_then_fill_holes",
        "inventory_work",
    ):
        assert v in fi.VERB_ENTRYPOINTS, v
        assert v in fi.wrapped_verbs(), v


def test_fr5775_update_intake_uses_shared_key(monkeypatch):
    posts: list[dict] = []

    def fake_post(title, body, *, repo, sig, exe):
        posts.append({"sig": sig, "title": title, "body": body})
        return {"ok": True}

    monkeypatch.setattr(fi, "intake_allowed", lambda **_k: True)
    monkeypatch.setattr(fi, "_native_post", fake_post)
    # Prefer shared helper over missing PS1 beside frozen module.
    out = fi.report_update_status_failure(
        product="airc",
        result="release-lookup-failed",
        tag="9.9.9",
        detail="",
        version="1.0.7",
        machine="marchhare",
    )
    assert out.get("ok") is True
    assert posts
    assert posts[0]["sig"] == (
        "airc-update-fail|marchhare|update|1.0.7|release-lookup-failed"
    )


def test_fr5775_packaged_path_skips_missing_ps1(monkeypatch, tmp_path):
    """Packaged airc.exe: no Report-*.ps1 in _MEIPASS; native post must still fire."""
    posts: list[dict] = []

    def fake_post(*a, **k):
        posts.append(k)
        return {"ok": True}

    monkeypatch.setattr(fi, "_meipass_dir", lambda: tmp_path)
    out = fi.report_verb_failure(
        "update",
        RuntimeError("spawn-failed"),
        version="1.0.7",
        machine="marchhare",
        wait_s=0,
        filer_post=fake_post,
    )
    assert out.get("ok") is True
    assert posts
    assert "skipped" not in out


def test_fr5775_ps1_helper_exists_and_matches_key():
    root = Path(fi.__file__).resolve().parents[1]
    ps1 = root / "scripts" / "Report-AircVerbFailure.ps1"
    assert ps1.is_file()
    text = ps1.read_text(encoding="utf-8")
    assert "airc-$Verb-fail" in text or 'airc-{0}-fail' in text or "airc-$(" in text
    assert "dedupe" in text.lower() or "IdempotencyKey" in text or "DedupeKey" in text
