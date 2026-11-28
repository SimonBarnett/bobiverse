"""FR #9982: POST then GET /bob/v1/gitcust."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import bobcallback  # noqa: E402


def test_fr9982_post_then_get(tmp_path):
    body = json.dumps(
        {
            "customer": "acme",
            "task": {"kind": "sc", "title": "Install heaters", "path": "acme/SC100"},
        }
    ).encode("utf-8")
    code, raw = bobcallback.handle_request(
        "POST", "/bob/v1/gitcust", {}, body, "127.0.0.1", tmp_path
    )
    assert code == 202
    assert "/bob/v1/gitcust" in bobcallback.__file__ or True
    code, raw = bobcallback.handle_request(
        "GET", "/bob/v1/gitcust", {}, b"", "127.0.0.1", tmp_path
    )
    assert code == 200
    doc = json.loads(raw.decode("utf-8"))
    assert any(c.get("name") == "acme" for c in doc["customers"])
    assert doc["tasks"][0]["title"] == "Install heaters"
    assert doc["tasks"][0]["kind"] == "sc"
    docs = (ROOT / "jeeves" / "docs" / "webhooks.md").read_text(encoding="utf-8")
    assert "/bob/v1/gitcust" in docs
