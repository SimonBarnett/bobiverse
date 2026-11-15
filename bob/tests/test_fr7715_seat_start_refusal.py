"""FR #7715: a seat-start refusal is one deduped intake report. A start is not."""
from __future__ import annotations

import bob_worker as bw


def _fuel():
    return bw.Fuel(opencode_free=None, opencode_go=None)


def _report(**kw):
    posts = []
    out = bw.report_seat_start_refusal(filer_post=posts.append, **kw)
    return posts, out


def test_fr7715_fuel_refusal_reports_once():
    posts, out = _report(
        machine="marchhare",
        kind="opencode",
        model="deepseek-v4-flash-free",
        reason="explicit opencode: no usable fuel (free=None go=None)",
        fuel=_fuel(),
        tray_restarted=False,
    )
    assert len(posts) == 1
    body = posts[0]["body"]
    assert "machine=marchhare" in body
    assert "kind=opencode" in body
    assert "deepseek-v4-flash-free" in body
    assert "no usable fuel" in body
    assert "opencode_free=None" in body
    assert "opencode_go=None" in body
    assert "tray_restarted=false" in body
    assert posts[0]["dedupe_key"] == out.get("key") or "key" in (out or {})
    assert "password=" not in body.lower()
    assert "Bearer" not in body


def test_fr7715_second_refusal_uses_the_same_key():
    a, _ = _report(
        machine="marchhare",
        kind="opencode",
        model="deepseek-v4-flash-free",
        reason="explicit opencode: no usable fuel (free=None go=None)",
        fuel=_fuel(),
    )
    b, _ = _report(
        machine="marchhare",
        kind="opencode",
        model="deepseek-v4-flash-free",
        reason="explicit opencode: no usable fuel (free=None go=None)",
        fuel=_fuel(),
    )
    assert a[0]["dedupe_key"] == b[0]["dedupe_key"]


def test_fr7715_normal_start_does_not_report():
    posts = []

    class Log:
        def __call__(self, _m):
            return None

    stopped = bw._explicit_refusal_exit(
        bw.Decision("opencode", "explicit opencode (free=1 go=0)"),
        Log(),
        "agent",
        machine="marchhare",
        kind="opencode",
        model="m",
        fuel=bw.Fuel(opencode_free=1, opencode_go=0),
        filer_post=posts.append,
    )
    assert stopped is None
    assert posts == []


def test_fr7715_secret_in_reason_is_redacted():
    posts, _ = _report(
        machine="marchhare",
        kind="opencode",
        model="m",
        reason="refused password=EXAMPLE_NOT_A_SECRET",
        fuel=_fuel(),
    )
    assert "EXAMPLE_NOT_A_SECRET" not in posts[0]["body"]
