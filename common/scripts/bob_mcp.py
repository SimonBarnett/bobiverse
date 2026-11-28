"""FR #10080: public POST /mcp for the Bob skill catalog. No token. No /bob/v1 change."""
from __future__ import annotations

import json
import os
from pathlib import Path

import bob_skill_catalog as catalog

MCP_PATH = "/mcp"
HOST = "https://bob.ntsa.uk"
_PRODUCTS = ("bob", "jeeves", "common", "airc")


def default_roots() -> list[Path]:
    """Skill books live in the bobiverse checkout, not inside the frozen exe.

    A webhook ``jeeves.exe`` extracts to ``_MEI*``. ``__file__`` there does not
    see ``C:\\ai\\bobiverse\\bob\\.grok\\skills``. Prefer that install tree, then
    ``BOB_REPO_ROOT``, then the repo that contains this file.
    """
    repos: list[Path] = []
    install = Path(r"C:\ai\bobiverse")
    if install.is_dir():
        repos.append(install)
    env_root = (os.environ.get("BOB_REPO_ROOT") or "").strip()
    if env_root:
        repos.append(Path(env_root))
    repos.append(Path(__file__).resolve().parents[2])
    found: list[Path] = []
    seen: set[str] = set()
    for repo in repos:
        for name in _PRODUCTS:
            root = repo / name / ".grok" / "skills"
            key = str(root).lower()
            if key in seen or not root.is_dir():
                continue
            seen.add(key)
            found.append(root)
    return found


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


def _skill_arg(args: dict | None) -> str:
    """Seats pass name, skill, or a SKILL.md path. The catalog key is the folder name."""
    data = args or {}
    raw = ""
    for key in ("name", "skill", "path"):
        val = str(data.get(key) or "").strip()
        if val:
            raw = val
            break
    raw = raw.replace("\\", "/").rstrip("/")
    if raw.lower().endswith("/skill.md"):
        raw = raw[: -len("/skill.md")]
    if "/" in raw:
        raw = raw.rsplit("/", 1)[-1]
    return raw


def _call(name: str, args: dict, roots: list[Path]) -> dict:
    if name == "list_catalog":
        return _tool_text(catalog.build_catalog(roots))
    if name == "get_skill":
        skill = catalog.load_skill(roots, _skill_arg(args))
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
                    {
                        "name": "list_catalog",
                        "description": "List public Bob skills",
                        "inputSchema": {"type": "object", "properties": {}},
                    },
                    {
                        "name": "get_skill",
                        "description": "Return one public SKILL.md",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "skill": {"type": "string"},
                                "path": {"type": "string"},
                            },
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
    if catalog.contains_secret(blob) and (
        "github_pat_" in catalog.prose_for_secret_scan(blob) or "ghp_" in catalog.prose_for_secret_scan(blob)
    ):
        err = {"jsonrpc": "2.0", "id": rid, "error": {"code": -32000, "message": "refused"}}
        return 500, json.dumps(err).encode("utf-8")
    return 200, blob.encode("utf-8")
