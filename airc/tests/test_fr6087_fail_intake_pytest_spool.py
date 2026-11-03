"""FR #6087: pytest fail-intake must not land in the live crash spool (then flush)."""
from __future__ import annotations

import airc_fail_intake as fi


def test_fr6087_forced_allowed_does_not_write_live_crash_spool(tmp_path, monkeypatch):
    """intake_allowed True + post failure must not write LOCALAPPDATA crash-spool.

    #6087 was the flushed spool of ValueError('gpo failed') from
    test_fr5775_spool_when_intake_down (title airc extension fail ValueError).
    """
    import crash_report as cr

    live = tmp_path / "live-crash-spool"
    live.mkdir()
    monkeypatch.setattr(cr, "spool_dir", lambda: live)
    monkeypatch.setattr(fi, "intake_allowed", lambda **_k: True)

    def boom(*_a, **_k):
        raise OSError("intake-unreachable")

    monkeypatch.setattr(fi, "_native_post", boom)
    out = fi.report_verb_failure(
        "extension",
        ValueError("gpo failed"),
        version="1.0.7",
        machine="ionos",
        wait_s=0,
    )
    assert out.get("ok") is False
    assert list(live.glob("*.json")) == []


def test_fr6087_flush_drops_gpo_failed_extension_fixture(tmp_path, monkeypatch):
    import crash_report as cr

    spool = tmp_path / "spool"
    spool.mkdir()
    row = spool / "crash-airc-extension-fail-fixture.json"
    row.write_text(
        '{"title":"airc extension fail ValueError","body":"gpo failed",'
        '"repo":"SimonBarnett/bobiverse","sig":"airc-extension-fail|ionos|extension|1.0.7|valueerror",'
        '"exe":"airc"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(cr, "spool_dir", lambda: spool)
    monkeypatch.setattr(
        cr,
        "load_crash_report_policy",
        lambda *a, **k: type("P", (), {"send": True})(),
    )
    posts: list[str] = []

    def fake_post(title, body, **_k):
        posts.append(title)
        return {"ok": True}

    out = cr.flush_spool(filer_post=fake_post)
    assert posts == []
    assert out.get("dropped") >= 1
    assert not row.exists()
