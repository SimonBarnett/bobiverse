"""FR #7347: start-up digest POST must pass hub schema; 4xx logs truncated body."""
from __future__ import annotations

import io
import json
from email.message import EmailMessage
from pathlib import Path

import bob_worker as bw
import bobcallback as bc
import bobreport as br
import registered_machines as rm
import urllib.error


def _plant_roster(home: Path, *machines: str) -> Path:
    chans = ["#bobiverse"] + [f"#{m}" for m in machines]
    rm.sync_from_chanserv(home, chans)
    return home


def _startup_payload(
    *,
    machine: str = "redqueen",
    pid: int = 6388,
    nick: str = "redqueen-6388",
    kind: str = "grok",
    state: str = "idle",
    assignable: bool | None = None,
) -> dict:
    """Mirror post_digest_seat_kind before any job/pool state exists."""
    payload = {
        "online": True,
        "id": machine,
        "pid": pid,
        "kind": kind,
        "state": state,
        "nick": nick,
        "working_on": "",
        "agent": kind,
        "worker_build": "39973a3070fa",
    }
    if assignable is False:
        payload["assignable"] = False
        payload["error"] = "needs-sign-in"
        payload["state"] = "needs_sign_in"
    elif assignable is True:
        payload["assignable"] = True
    return payload


def test_fr7347_startup_idle_payload_accepted_by_hub(tmp_path):
    home = _plant_roster(tmp_path, "redqueen")
    raw = _startup_payload()
    coerced = bc.coerce_report_payload(raw)
    code, mid, why = bc.validate_report_payload(home, coerced)
    assert code == 0, why
    assert mid == "redqueen"
    assert coerced.get("op") in bc.WORKER_OPS
    assert coerced.get("state") == "idle"
    out = br.apply_callback(home, coerced)
    assert out.ok, out.err


def test_fr7347_startup_needs_sign_in_payload_accepted(tmp_path):
    home = _plant_roster(tmp_path, "redqueen")
    for raw_state in ("needs_sign_in", "needs-sign-in"):
        raw = _startup_payload(state=raw_state, assignable=False if raw_state == "needs-sign-in" else None)
        if raw_state == "needs_sign_in":
            raw["state"] = "needs_sign_in"
        coerced = bc.coerce_report_payload(raw)
        code, mid, why = bc.validate_report_payload(home, coerced)
        assert code == 0, (raw_state, why, coerced)
        assert coerced.get("state") == "needs_sign_in"
        out = br.apply_callback(home, coerced)
        assert out.ok, (raw_state, out.err)
        rows = br.load_digest(home)["machines"]["redqueen"].get("worker_list") or []
        assert any(r.get("state") == "needs_sign_in" for r in rows), rows


def test_fr7347_unhealthy_state_accepted(tmp_path):
    home = _plant_roster(tmp_path, "redqueen")
    raw = _startup_payload(state="unhealthy")
    coerced = bc.coerce_report_payload(raw)
    code, mid, why = bc.validate_report_payload(home, coerced)
    assert code == 0, why
    assert coerced.get("state") == "unhealthy"
    out = br.apply_callback(home, coerced)
    assert out.ok, out.err


def test_fr7347_post_digest_normalizes_hyphen_state(monkeypatch):
    seen = {}

    def fake_post(url, payload, **kw):  # noqa: ARG001
        seen.update(payload)
        return True

    monkeypatch.setattr(bw, "_http_post_json", fake_post)
    ok = bw.post_digest_seat_kind(
        machine="redqueen",
        pid=6388,
        nick="redqueen-6388",
        kind="grok",
        assignable=False,
    )
    assert ok is True
    assert seen.get("state") == "needs_sign_in"
    assert seen.get("error") == "needs-sign-in"


def _http_error(code=400, *, server="cloudflare", ray="a5a8a4716ec23eca-LHR", body=b'{"error":"bad state"}'):
    hdrs = EmailMessage()
    if server:
        hdrs["Server"] = server
    if ray:
        hdrs["CF-Ray"] = ray
    return urllib.error.HTTPError(
        "https://bob.ntsa.uk/bob/v1/report",
        int(code),
        "Bad Request",
        hdrs,
        io.BytesIO(body),
    )


def test_fr7347_4xx_logs_status_responder_ray_and_body(monkeypatch):
    logs: list[str] = []

    def fake_urlopen(req, timeout=None):  # noqa: ARG001
        raise _http_error()

    monkeypatch.setattr(bw.urllib.request, "urlopen", fake_urlopen)
    ok = bw._http_post_json(
        "https://bob.ntsa.uk/bob/v1/report",
        {"id": "redqueen", "pid": 6388, "kind": "grok", "state": "idle", "nick": "redqueen-6388"},
        log=logs.append,
        retries=1,
    )
    assert ok is False
    blob = " ".join(logs)
    assert "400" in blob
    assert "cloudflare" in blob.lower()
    assert "a5a8a4716ec23eca-LHR" in blob
    assert "bad state" in blob
    assert "FAKE_" not in blob
    meta = bw.last_digest_http()
    assert meta.get("status") == 400
    assert meta.get("responder") == "cloudflare"
    assert meta.get("ray") == "a5a8a4716ec23eca-LHR"
    assert "bad state" in (meta.get("body") or "")


def test_fr7347_4xx_body_truncated_and_scrubbed(monkeypatch):
    long_body = ("x" * 250) + " password=hunter2-should-not-persist"
    logs: list[str] = []

    def fake_urlopen(req, timeout=None):  # noqa: ARG001
        raise _http_error(body=long_body.encode("utf-8"))

    monkeypatch.setattr(bw.urllib.request, "urlopen", fake_urlopen)
    bw._http_post_json(
        "https://bob.ntsa.uk/bob/v1/report",
        {"id": "redqueen", "pid": 1, "nick": "redqueen-1", "state": "idle"},
        log=logs.append,
        retries=1,
    )
    blob = " ".join(logs)
    assert "hunter2" not in blob
    meta = bw.last_digest_http()
    body = meta.get("body") or ""
    assert len(body) <= 200
    assert "hunter2" not in body


def test_fr7347_hub_reject_returns_error_body(tmp_path):
    home = _plant_roster(tmp_path, "redqueen")
    code, body = bc.handle_report_post(
        {"Content-Type": "application/json"},
        json.dumps(
            {
                "op": "worker-work",
                "id": "redqueen",
                "nick": "redqueen-1",
                "pid": 1,
                "state": "not-a-real-state",
            }
        ).encode("utf-8"),
        home,
    )
    assert code == 400
    assert body
    parsed = json.loads(body.decode("utf-8"))
    assert parsed.get("error") == "bad state"
