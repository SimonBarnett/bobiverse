"""FR #7527: valid Jeeves login is JSON 200; failures are JSON, never a bare 404."""
from __future__ import annotations

import json
import socket
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError, URLError

import bobcallback
import jeeves_settings_http as http

# FR #3304: assemble placeholders from parts (never contiguous password= hunter bait).
_FAKE_OK = "FAKE_" + "login_ok"
_FAKE_BAD = "FAKE_" + "login_bad"


def _port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _post(port: int, payload: dict) -> tuple[int, dict, str]:
    body = json.dumps(payload).encode("utf-8")
    req = __import__("urllib.request").request.Request(
        f"http://127.0.0.1:{port}/jeeves/api/login",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with __import__("urllib.request").request.urlopen(req, timeout=5) as resp:
            raw = resp.read()
            cookie = resp.headers.get("Set-Cookie") or ""
            return int(resp.status), json.loads(raw.decode("utf-8")), cookie
    except HTTPError as exc:
        raw = exc.read()
        try:
            doc = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            doc = {"_bare": raw.decode("utf-8", errors="replace")}
        return int(exc.code), doc, ""


def test_fr7527_valid_forms_bad_domain_and_internal(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
    home = tmp_path / "h"
    home.mkdir()
    reports: list[str] = []

    def auther(user: str, password: str, domain: str = "") -> bool:
        if domain == "explode.example":
            raise RuntimeError("authenticator fault")
        if domain == "no-such.example":
            return False
        if password != _FAKE_OK:
            return False
        return (user == "ada" and domain == "wonder.example") or (
            user == "ada" and domain == "WONDER"
        )

    def _report(exe, exc_type, exc_value, tb, **kwargs):
        reports.append(str(exc_type.__name__ if exc_type else ""))
        assert _FAKE_OK not in str(exc_value)
        return {"ok": True, "skipped": True}

    import crash_report

    monkeypatch.setattr(crash_report, "report_exception", _report)
    port = _port()
    srv = http.start_settings_http(home, bind="127.0.0.1", port=port, authenticator=auther)
    assert srv is not None
    try:
        code, doc, cookie = _post(
            port, {"username": "ada@wonder.example", "password": _FAKE_OK}
        )
        assert code == 200 and doc.get("ok") is True
        assert "jeeves_appliance_session=" in cookie
        assert doc.get("error") is None

        code, doc, _cookie = _post(
            port, {"username": r"WONDER\ada", "password": _FAKE_OK}
        )
        assert code == 200 and doc.get("ok") is True

        code, doc, _cookie = _post(
            port, {"username": "ada@wonder.example", "password": _FAKE_BAD}
        )
        assert code == 401 and doc.get("ok") is False
        assert str(doc.get("error") or "").startswith("unauthorized")

        code, doc, _cookie = _post(
            port, {"username": "ada@no-such.example", "password": _FAKE_OK}
        )
        assert code == 401 and doc.get("ok") is False
        assert "error" in doc

        code, doc, _cookie = _post(
            port, {"username": "ada@explode.example", "password": _FAKE_OK}
        )
        assert code == 500 and doc.get("ok") is False
        assert str(doc.get("error") or "").startswith("internal")
        assert reports
        assert "_bare" not in doc
    finally:
        http.stop_settings_http(srv)


def test_fr7527_proxy_outage_is_json_not_bare_404(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()

    def _boom(req, timeout=8):
        assert timeout >= 30
        raise URLError("timed out")

    monkeypatch.setattr(bobcallback, "urlopen", _boom)
    bobcallback.stash_response_headers([])
    code, body = bobcallback.handle_request(
        "POST",
        "/jeeves/api/login",
        {"Content-Type": "application/json"},
        json.dumps({"username": "ada@wonder.example", "password": _FAKE_OK}).encode("utf-8"),
        "8.8.8.8",
        home,
        set(),
    )
    assert code == 502
    doc = json.loads(body.decode("utf-8"))
    assert doc.get("ok") is False
    assert "error" in doc
    assert body != b""
