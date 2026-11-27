"""FR #10080: public POST /mcp for the Bob skill catalog. No token. No /bob/v1 change."""
from __future__ import annotations

import json
from pathlib import Path

import bob_skill_catalog as catalog

MCP_PATH = "/mcp"
HOST = "https://bob.ntsa.uk"


def default_roots() -> list[Path]:
    repo = Path(__file__).resolve().parents[2]
    return [repo / name / ".grok" / "skills" for name in ("bob", "jeeves", "common", "airc")]


def describe() -> dict:
    return {
        "ok": True,
        "origin": HOST,
        "transport": "POST JSON-RPC to /mcp",
        "protocolVersion": "2024-11-05",
        "tools": ["list_catalog", "get_skill"],
        "note": "Bob agent skill catalog. No secrets. stdio is not served here.",
    }


def _tool_text(payload: dict) -> dict:
    return {
        "content": [
            {"type": "text", "text": json.dumps(payload, indent=2)}
        ]
    }


def _call(name: str, args: dict, roots: list[Path]) -> dict:
    if name == "list_catalog":
        return _tool_text(catalog.build_catalog(roots))
    if name == "get_skill":
        skill = catalog.load_skill(roots, str((args or {}).get("name") or ""))
        if skill is None:
            return {"isError": True, "content": [{"type": "text", "text": "unknown skill"}]}
        return _tool_text(
            {
                "name": skill["name"],
                "title": skill["title"],
                "description": skill["description"],
                "skillMd": skill["skillMd"],
            }
        )
    raise KeyError(name)


def handle_mcp(verb: str, body: bytes | str, roots: list[Path] | None = None) -> tuple[int, bytes]:
    roots = roots if roots is not None else default_roots()
    if verb in ("GET", "HEAD"):
        payload = json.dumps(describe()).encode("utf-8")
        return 200, b"" if verb == "HEAD" else payload
    if verb != "POST":
        return 405, b""
    raw = body.encode("utf-8") if isinstance(body, str) else body
    try:
        req = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        req = None
    if not isinstance(req, dict):
        err = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        return 400, json.dumps(err).encode("utf-8")
    rid = req.get("id")
    method = str(req.get("method") or "")
    params = req.get("params") if isinstance(req.get("params"), dict) else {}
    try:
        if method in ("initialize",):
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "bob-skill-catalog", "version": "1"},
            }
        elif method == "tools/list":
            result = {
                "tools": [
                    {"name": "list_catalog", "description": "List public Bob skills"},
                    {
                        "name": "get_skill",
                        "description": "Return one public SKILL.md",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"name": {"type": "string"}},
                            "required": ["name"],
                        },
                    },
                ]
            }
        elif method == "tools/call":
            result = _call(str(params.get("name") or ""), params.get("arguments") or {}, roots)
        else:
            err = {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "method not found"}}
            return 200, json.dumps(err).encode("utf-8")
    except KeyError:
        err = {"jsonrpc": "2.0", "id": rid, "error": {"code": -32602, "message": "unknown tool"}}
        return 200, json.dumps(err).encode("utf-8")
    out = {"jsonrpc": "2.0", "id": rid, "result": result}
    blob = json.dumps(out)
    if "github_pat_" in blob or "ghp_" in blob:
        err = {"jsonrpc": "2.0", "id": rid, "error": {"code": -32000, "message": "refused"}}
        return 500, json.dumps(err).encode("utf-8")
    return 200, blob.encode("utf-8")
