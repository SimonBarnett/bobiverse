"""FR #7148: unavailable configured start model -> shop + intake; never premium fallback."""
from __future__ import annotations

import bob_worker as bw
import worker_start_model as wsm


def test_fr7148_empty_configured_skips_intake():
    posts = []
    out = bw.report_configured_start_model_unavailable(
        kind="grok",
        configured="",
        actual="",
        machine="redqueen",
        reason="unavailable",
        filer_post=lambda p: posts.append(p) or {"ok": True},
        shop_say=lambda *a, **k: True,
        log=lambda m: None,
    )
    assert out.get("skipped") is True
    assert posts == []


def test_fr7148_unavailable_files_intake_and_shop_no_secrets():
    posts = []
    shops = []
    logs = []
    out = bw.report_configured_start_model_unavailable(
        kind="grok",
        configured="EXAMPLE_GROK_MIN",
        actual="EXAMPLE_GROK_MAX",
        machine="redqueen",
        nick="redqueen-99",
        reason="mismatch",
        filer_post=lambda p: posts.append(p) or {"ok": True},
        shop_say=lambda ch, msg: shops.append((ch, msg)) or True,
        log=lambda m: logs.append(m),
        shop="redqueen",
    )
    assert out.get("ok") is True
    assert len(posts) == 1
    body = posts[0]["body"]
    title = posts[0]["title"]
    assert "EXAMPLE_GROK_MIN" in body
    assert "unavailable" in title.lower() or "start model" in title.lower()
    assert "password" not in body.lower()
    assert "token" not in body.lower()
    assert "Bearer" not in body
    assert posts[0]["repo"] == "SimonBarnett/bobiverse"
    assert shops and "EXAMPLE_GROK_MIN" in shops[0][1]
    assert "no premium fallback" in shops[0][1].lower() or "no substitute" in shops[0][1].lower()
    assert logs


def test_fr7148_launch_argv_never_invents_premium():
    argv = ["grok.exe", "run"]
    assert wsm.launch_argv_with_model("grok", argv, "") == ["grok.exe", "run"]
    got = wsm.launch_argv_with_model("grok", argv, "EXAMPLE_GROK_MIN")
    assert got[1:3] == ["--model", "EXAMPLE_GROK_MIN"]
    assert "EXAMPLE_GROK_MAX" not in got


def test_fr7148_post_launch_mismatch_calls_report(monkeypatch):
    calls = []

    def fake_report(**kwargs):
        calls.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(bw, "report_configured_start_model_unavailable", fake_report)
    # Drive the small helper that post-launch uses.
    bw.notify_start_model_after_launch(
        kind="cursor",
        configured="EXAMPLE_CUR_MIN",
        actual="EXAMPLE_CUR_MAX",
        machine="flamingo",
        nick="flamingo-1",
        shop_say=lambda *a, **k: True,
        log=lambda m: None,
        shop="flamingo",
    )
    assert len(calls) == 1
    assert calls[0]["configured"] == "EXAMPLE_CUR_MIN"
    assert calls[0]["actual"] == "EXAMPLE_CUR_MAX"


def test_fr7148_post_launch_match_skips_report(monkeypatch):
    calls = []
    monkeypatch.setattr(
        bw,
        "report_configured_start_model_unavailable",
        lambda **kwargs: calls.append(kwargs) or {"ok": True},
    )
    bw.notify_start_model_after_launch(
        kind="grok",
        configured="EXAMPLE_GROK_MIN",
        actual="EXAMPLE_GROK_MIN",
        machine="redqueen",
        nick="redqueen-1",
        shop_say=lambda *a, **k: True,
        log=lambda m: None,
        shop="redqueen",
    )
    assert calls == []
