"""FR #10080: POST /mcp list_catalog and get_skill. GET describes the endpoint."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import bob_mcp  # noqa: E402
import bobcallback  # noqa: E402

HOME = Path(__file__).resolve().parents[2] / "jeeves" / "www" / "irc-ntsa" / "index.html"


def _roots(tmp_path: Path) -> list[Path]:
    skill = tmp_path / "bob-shop" / "SKILL.md"
    skill.parent.mkdir()
    skill.write_text(
        "---\nname: bob-shop\ndescription: Shop wire.\n---\n\n# Shop\n\nhello\n",
        encoding="utf-8",
    )
    return [tmp_path]


def test_get_describes_without_a_token():
    code, body = bob_mcp.handle_mcp("GET", b"")
    doc = json.loads(body)
    assert code == 200
    assert doc["tools"] == ["list_catalog", "get_skill"]
    assert "token" not in json.dumps(doc).lower()


def test_post_list_and_get(tmp_path: Path):
    roots = _roots(tmp_path)
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "list_catalog", "arguments": {}},
    }
    code, body = bob_mcp.handle_mcp("POST", json.dumps(req).encode(), roots)
    assert code == 200
    listed = json.loads(json.loads(body)["result"]["content"][0]["text"])
    assert listed["skills"][0]["name"] == "bob-shop"
    req["id"] = 2
    req["params"] = {"name": "get_skill", "arguments": {"name": "bob-shop"}}
    code, body = bob_mcp.handle_mcp("POST", json.dumps(req).encode(), roots)
    skill = json.loads(json.loads(body)["result"]["content"][0]["text"])
    assert "hello" in skill["skillMd"]
    assert "github_pat_" not in body.decode()


def test_callback_routes_mcp_and_home_card(tmp_path: Path):
    code, body = bobcallback.handle_request("GET", "/mcp", {}, b"", "127.0.0.1", tmp_path)
    assert code == 200
    assert b"list_catalog" in body
    code, body = bobcallback.handle_request("GET", "/bob/v1/models", {}, b"", "127.0.0.1", tmp_path)
    assert code != 404 or b"agents" in body or code in (200, 503)
    text = HOME.read_text(encoding="utf-8")
    assert "https://bob.ntsa.uk/mcp" in text
    assert "Bob DAG" in text
    assert "https://mcp.ntsa.uk" in text
