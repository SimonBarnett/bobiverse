"""FR #10032: GET health and POST /bob/v1/ask validation."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ask_webhook as ask  # noqa: E402
import bobcallback  # noqa: E402


def test_get_health():
    code, body = ask.health()
    assert code == 200
    assert json.loads(body)["ok"] is True


def test_post_requires_sc_and_correlation():
    code, body = ask.handle_post(b"{}")
    assert code == 400
    assert json.loads(body)["error"] == "bad_sc"
    good = json.dumps({"sc": "acme", "correlation_id": "c-1", "text": "hello"}).encode()
    code, body = ask.handle_post(good)
    assert code == 202
    assert json.loads(body)["correlation_id"] == "c-1"
    assert "acme" not in body.decode()


def test_callback_routes(tmp_path: Path):
    code, body = bobcallback.handle_request(
        "GET", "/bob/v1/ask/health", {}, b"", "127.0.0.1", tmp_path
    )
    assert code == 200
    assert b'"ok": true' in body
    code, body = bobcallback.handle_request(
        "POST",
        "/bob/v1/ask",
        {},
        json.dumps({"sc": "acme", "correlation_id": "c-2"}).encode(),
        "127.0.0.1",
        tmp_path,
    )
    assert code == 202
