"""FR #6060: native WCF PRIORITY wcf prepare form (no WINRUN / node SDK)."""
from __future__ import annotations

import json

import airc_priority as ap
import priority_wcf as wcf


def _pw() -> str:
    return "FAKE_" + "PREP" + "60"


def test_fr6060_refuse_without_ename():
    seen = []

    def fake_post(url, data, headers, timeout_s=30.0):
        seen.append(headers.get("SOAPAction"))
        return 400, ""

    out = wcf.run_priority_wcf(
        "PRIORITY wcf prepare form url=https://priority.example.invalid user=tabula",
        passed_password=_pw(),
        http_post=fake_post,
        mode="direct",
    )
    assert out.get("ok") is False
    assert out.get("error") == "ename_missing"
    assert seen == []
    assert _pw() not in str(out)


def test_fr6060_parse_wcf_prepare_form():
    p = wcf.parse_priority_wcf_command(
        "id=aabb6060 PRIORITY wcf prepare form WWWSHOWCUST hrs-dev-live1"
    )
    assert p is not None
    assert p["kind"] == "prepare_form"
    assert p["ename"] == "WWWSHOWCUST"
    assert p["instance"] == "hrs-dev-live1"
    assert p["job_id"] == "aabb6060"


def test_fr6060_compact_reply_keys():
    payload = {
        "action": "wcf",
        "ok": True,
        "op": "prepare",
        "ename": "WWWSHOWCUST",
        "steps": 3,
        "last_type": "end",
        "last_message": "prep ok",
        "errs": 1,
        "via": "wcf",
    }
    framed, code = ap.format_bounded_priority_out("aabb6060", payload, 0)
    assert code == 0
    assert len(framed.encode("utf-8")) <= ap.PRIORITY_REPLY_MAX_BYTES
    body = json.loads(framed.split("seq=1 ", 1)[1])
    assert body.get("ok") is True
    assert body.get("ename") == "WWWSHOWCUST"
