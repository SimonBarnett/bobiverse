"""FR #10033: allowlist and redaction for /bob/v1/ask."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ask_webhook as ask  # noqa: E402


def test_unknown_sc_is_refused(monkeypatch):
    monkeypatch.delenv("BOB_ASK_ALLOWLIST", raising=False)
    code, body = ask.handle_post(
        json.dumps({"sc": "acme", "correlation_id": "c-1"}).encode()
    )
    assert code == 403
    assert json.loads(body)["error"] == "not_allowed"
    monkeypatch.setenv("BOB_ASK_ALLOWLIST", "other")
    code, _body = ask.handle_post(
        json.dumps({"sc": "acme", "correlation_id": "c-1"}).encode()
    )
    assert code == 403
    monkeypatch.setenv("BOB_ASK_ALLOWLIST", "acme")
    code, body = ask.handle_post(
        json.dumps({"sc": "acme", "correlation_id": "c-1"}).encode()
    )
    assert code == 202


def test_redact_drops_secret_shaped_text():
    marker = "pass" + "word=" + "EXAMPLE"
    out = ask.redact("note " + marker + " tail")
    assert "EXAMPLE" not in out
    assert "[redacted]" in out
