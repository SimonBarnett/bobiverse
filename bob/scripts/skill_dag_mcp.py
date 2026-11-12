"""FR #6862: local stdio skill-dag MCP (resolve, get_skill, status). No listen port."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROTOCOL = "2024-11-05"
DEFAULT_MAX_BYTES = 65536
JOB_SEEDS = {
    "FR": "bobiverse-bob-job-fr",
    "MRB": "bobiverse-bob-job-mrb",
    "UAT": "bobiverse-bob-job-uat",
    "FIX": "bobiverse-bob-job-fr",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---"):
        return {}
    rest = text[3:]
    end = rest.find("\n---")
    if end < 0:
        return {}
    block = rest[:end]
    meta: dict[str, Any] = {}
    key = ""
    for raw in block.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.lstrip().startswith("- ") and key == "depends_on":
            item = line.split("-", 1)[1].strip().strip("\"'")
            meta.setdefault("depends_on", []).append(item)
            continue
        if ":" in line and not line.startswith(" "):
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip().strip("\"'")
            if key == "depends_on":
                meta["depends_on"] = []
                if val and val not in ("[]",):
                    inner = val.strip("[]")
                    meta["depends_on"] = [p.strip().strip("\"'") for p in inner.split(",") if p.strip()]
            else:
                meta[key] = val
    meta.setdefault("depends_on", [])
    return meta


def _under_roots(path: Path, roots: list[Path]) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


class SkillDagServer:
    def __init__(self, *, roots: list[Path], max_bytes: int = DEFAULT_MAX_BYTES) -> None:
        self.roots = [Path(r) for r in roots]
        self.max_bytes = int(max_bytes or DEFAULT_MAX_BYTES)
        self.last_error = ""
        self.index_time = ""
        self.nodes: dict[str, dict[str, Any]] = {}
        self.rebuild()

    def rebuild(self) -> None:
        nodes: dict[str, dict[str, Any]] = {}
        err = ""
        try:
            for root in self.roots:
                if not root.is_dir():
                    continue
                for skill in root.rglob("SKILL.md"):
                    if not skill.is_file():
                        continue
                    text = skill.read_text(encoding="utf-8")
                    meta = _parse_frontmatter(text)
                    sid = str(meta.get("name") or skill.parent.name).strip()
                    if not sid:
                        continue
                    body = text
                    if text.startswith("---"):
                        rest = text[3:]
                        cut = rest.find("\n---")
                        if cut >= 0:
                            body = rest[cut + 4 :]
                    nodes[sid] = {
                        "id": sid,
                        "description": str(meta.get("description") or "").strip(),
                        "depends_on": list(meta.get("depends_on") or []),
                        "path": str(skill.resolve()),
                        "bytes": len(text.encode("utf-8")),
                        "body": body,
                    }
        except Exception as exc:  # noqa: BLE001
            err = type(exc).__name__
        self.nodes = nodes
        self.index_time = _utc_now()
        self.last_error = err

    def tools_list(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "resolve",
                "description": "Matched skill ids plus depends_on ancestors; skip when over budget.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"seed": {"type": "string"}},
                    "required": ["seed"],
                },
            },
            {
                "name": "get_skill",
                "description": "Return one SKILL.md body if the path is under configured roots.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
            {
                "name": "status",
                "description": "Index time, node count, last error.",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]

    def _seed_id(self, seed: str) -> str:
        raw = str(seed or "").strip()
        up = raw.upper()
        if up in JOB_SEEDS:
            return JOB_SEEDS[up]
        return raw

    def _closure(self, seed_id: str) -> list[str]:
        seen: set[str] = set()
        order: list[str] = []

        def walk(sid: str) -> None:
            if sid in seen or sid not in self.nodes:
                return
            seen.add(sid)
            node = self.nodes[sid]
            for dep in node.get("depends_on") or []:
                walk(str(dep))
            order.append(sid)

        walk(seed_id)
        return order

    def resolve(self, seed: str) -> dict[str, Any]:
        sid = self._seed_id(seed)
        matched: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        used = 64
        for nid in self._closure(sid):
            node = self.nodes[nid]
            item = {
                "id": node["id"],
                "description": node["description"],
                "depends_on": list(node["depends_on"]),
                "path": node["path"],
                "bytes": node["bytes"],
            }
            piece = json.dumps(item, ensure_ascii=False)
            cost = len(piece.encode("utf-8")) + node["bytes"]
            if used + cost > self.max_bytes:
                skipped.append({"id": nid, "reason": "over_budget"})
                continue
            used += cost
            matched.append(item)
        return {"matched": matched, "skipped": skipped}

    def get_skill(self, path: str) -> dict[str, Any]:
        try:
            p = Path(path)
            if not p.exists():
                return {"ok": False, "reason": "not_found"}
            resolved = p.resolve()
        except OSError:
            return {"ok": False, "reason": "not_found"}
        if not _under_roots(resolved, self.roots):
            return {"ok": False, "reason": "path_refused"}
        raw = resolved.read_bytes()
        if len(raw) > self.max_bytes:
            return {"ok": False, "reason": "over_budget", "bytes": len(raw)}
        return {"ok": True, "path": str(resolved), "body": raw.decode("utf-8")}

    def status(self) -> dict[str, Any]:
        return {
            "index_time": self.index_time,
            "node_count": len(self.nodes),
            "last_error": self.last_error,
        }

    def call_tool(self, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        args = arguments or {}
        if name == "resolve":
            return self.resolve(str(args.get("seed") or args.get("job") or ""))
        if name == "get_skill":
            return self.get_skill(str(args.get("path") or ""))
        if name == "status":
            return self.status()
        return {"ok": False, "reason": "unknown_tool"}

    def handle_rpc(self, msg: dict[str, Any]) -> dict[str, Any] | None:
        method = str(msg.get("method") or "")
        mid = msg.get("id")
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": mid,
                "result": {
                    "protocolVersion": PROTOCOL,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "skill-dag", "version": "0.1.0"},
                },
            }
        if method == "notifications/initialized":
            return None
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": mid, "result": {"tools": self.tools_list()}}
        if method == "tools/call":
            params = msg.get("params") or {}
            name = str(params.get("name") or "")
            result = self.call_tool(name, params.get("arguments") or {})
            text = json.dumps(result, ensure_ascii=False)
            return {
                "jsonrpc": "2.0",
                "id": mid,
                "result": {"content": [{"type": "text", "text": text}]},
            }
        if mid is None:
            return None
        return {
            "jsonrpc": "2.0",
            "id": mid,
            "error": {"code": -32601, "message": "method not found"},
        }


def serve_stdio(server: SkillDagServer, inf, outf) -> None:
    for line in inf:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        reply = server.handle_rpc(msg)
        if reply is not None:
            outf.write(json.dumps(reply, ensure_ascii=False) + "\n")
            outf.flush()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="FR #6862 stdio skill-dag MCP")
    p.add_argument("--root", action="append", default=[], help="Allowlisted skill root (repeatable)")
    p.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    args = p.parse_args(argv)
    roots = [Path(r) for r in (args.root or [])]
    if not roots:
        here = Path(__file__).resolve()
        pack = here.parents[1] / ".grok" / "skills"
        if pack.is_dir():
            roots = [pack]
    server = SkillDagServer(roots=roots, max_bytes=args.max_bytes)
    serve_stdio(server, sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
