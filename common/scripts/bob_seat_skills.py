"""FR #10081: a seat loads a Bob skill from https://bob.ntsa.uk/mcp.

Git remains the publish source. This read does not clone or fetch .grok/skills.
"""
from __future__ import annotations

import json
import os
import urllib.request

DEFAULT_URL = "https://bob.ntsa.uk/mcp"


def fetch_skill(name: str, url: str | None = None, opener=None) -> str:
    endpoint = (url or os.environ.get("BOB_SKILL_MCP_URL") or DEFAULT_URL).strip()
    req_body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "get_skill", "arguments": {"name": name}},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=req_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    open_url = opener or urllib.request.urlopen
    with open_url(request, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("error"):
        raise RuntimeError("mcp error")
    content = payload["result"]["content"][0]["text"]
    doc = json.loads(content)
    md = str(doc.get("skillMd") or "")
    if not md:
        raise RuntimeError("empty skill")
    return md


def load_seat_skill(name: str, url: str | None = None, opener=None) -> str:
    """Seat start path for one named playbook."""
    return fetch_skill(name, url=url, opener=opener)
