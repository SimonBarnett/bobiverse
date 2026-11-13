"""FR #6862/#6901: local stdio skill-dag MCP (resolve, get_skill, status). No listen port.

FR #6901: resolve scores the job line against skill descriptions when the first
token is not FR/MRB/UAT/FIX and the line is not an exact skill id.
"""
from __future__ import annotations

import argparse
import json
import re
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
_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "to",
        "of",
        "for",
        "in",
        "on",
        "is",
        "are",
        "be",
        "with",
        "from",
        "by",
        "at",
        "as",
        "it",
        "this",
        "that",
        "do",
        "does",
        "please",
        "run",
        "via",
    }
)


def _tokens(text: str) -> set[str]:
    return {
        t
        for t in _TOKEN_RE.findall(str(text or "").lower())
        if len(t) > 1 and t not in _STOPWORDS
    }


def score_description(job_line: str, description: str) -> int:
    """Count overlapping content tokens between the job line and a skill description."""
    job = _tokens(job_line)
    desc = _tokens(description)
    if not job or not desc:
        return 0
    return len(job & desc)


class JobSkillsRootRefused(ValueError):
    """Raised when a proposed job skills root is not the assigned worktree .grok/skills."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def job_skills_dir(worktree: Path) -> Path:
    """Assigned job worktree skill root (FR #6866)."""
    return (Path(worktree) / ".grok" / "skills").resolve()


def accept_job_skills_root(root: Path, *, assigned_worktree: Path) -> Path:
    """Accept only ``assigned_worktree/.grok/skills``; refuse sibling repo paths."""
    expected = job_skills_dir(assigned_worktree)
    try:
        got = Path(root).resolve()
    except OSError as exc:
        raise JobSkillsRootRefused(str(exc)) from exc
    if got != expected:
        raise JobSkillsRootRefused(f"refused {got}; expected {expected}")
    return got


def build_roots(
    *,
    base_roots: list[Path] | None = None,
    job_worktree: Path | None = None,
) -> tuple[list[Path], str]:
    """Compose allowlisted roots. Optional job worktree adds only that ``.grok/skills``."""
    roots = [Path(r) for r in (base_roots or [])]
    err = ""
    if job_worktree is not None:
        skills = Path(job_worktree) / ".grok" / "skills"
        if skills.is_dir():
            try:
                roots.append(accept_job_skills_root(skills, assigned_worktree=job_worktree))
            except JobSkillsRootRefused as exc:
                err = str(exc)
        # Missing skills dir: skip (optional root only after the path exists).
    # De-dupe while preserving order
    seen: set[str] = set()
    out: list[Path] = []
    for r in roots:
        key = str(r.resolve()) if r.exists() else str(r)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out, err


def roots_from_argv(argv: list[str] | None = None) -> list[Path]:
    """Parse ``--root`` / ``--job-worktree`` the same way as ``main`` (no stdio serve)."""
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--root", action="append", default=[])
    p.add_argument("--job-worktree", default=None)
    p.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    args, _unknown = p.parse_known_args(argv)
    base = [Path(r) for r in (args.root or [])]
    if not base and not args.job_worktree:
        here = Path(__file__).resolve()
        pack = here.parents[1] / ".grok" / "skills"
        if pack.is_dir():
            base = [pack]
    job_wt = Path(args.job_worktree) if args.job_worktree else None
    roots, err = build_roots(base_roots=base, job_worktree=job_wt)
    if err:
        raise JobSkillsRootRefused(err)
    return roots


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
    folded_key = ""
    folded_lines: list[str] = []

    def flush_fold() -> None:
        nonlocal folded_key, folded_lines
        if folded_key:
            meta[folded_key] = " ".join(x for x in folded_lines if x).strip()
            folded_key = ""
            folded_lines = []

    for raw in block.splitlines():
        line = raw.rstrip()
        if folded_key:
            if line.startswith((" ", "\t")):
                folded_lines.append(line.strip())
                continue
            flush_fold()
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
            elif val in (">", "|", ">-", "|-", ">+", "|+"):
                folded_key = key
                folded_lines = []
            else:
                meta[key] = val
    flush_fold()
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
            from skill_dag_index import format_name_collisions, scan_skills_with_collisions

            slim, collisions = scan_skills_with_collisions(self.roots)
            for item in slim:
                skill = Path(item["path"])
                text = skill.read_text(encoding="utf-8") if skill.is_file() else ""
                body = text
                if text.startswith("---"):
                    rest = text[3:]
                    cut = rest.find("\n---")
                    if cut >= 0:
                        body = rest[cut + 4 :]
                nodes[item["id"]] = {**item, "body": body}
            err = format_name_collisions(collisions)
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
        """Map FR/MRB/UAT/FIX, else exact node id, else description score winner (FR #6901)."""
        raw = str(seed or "").strip()
        if not raw:
            return raw
        first = raw.split(None, 1)[0].upper()
        if first in JOB_SEEDS:
            return JOB_SEEDS[first]
        if raw in self.nodes:
            return raw
        first_raw = raw.split(None, 1)[0]
        if first_raw in self.nodes:
            return first_raw
        best_id = ""
        best_score = 0
        for nid, node in self.nodes.items():
            sc = score_description(raw, str(node.get("description") or ""))
            if sc > best_score or (sc == best_score and sc > 0 and (not best_id or nid < best_id)):
                best_score = sc
                best_id = nid
        return best_id if best_score > 0 else ""

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
        if not sid:
            return {"matched": matched, "skipped": skipped}
        used = 64
        order = self._closure(sid)
        if sid in order:
            order = [sid] + [nid for nid in order if nid != sid]
        for nid in order:
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
    p = argparse.ArgumentParser(description="FR #6862/#6866 stdio skill-dag MCP")
    p.add_argument("--root", action="append", default=[], help="Allowlisted skill root (repeatable)")
    p.add_argument(
        "--job-worktree",
        default=None,
        help="Optional assigned job worktree; adds only <wt>/.grok/skills when it exists (FR #6866)",
    )
    p.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    # FR #7000: Cursor agent seats may lack a skill-dag MCP namespace in dynamic tools;
    # one-shot resolve/get_skill/status prints JSON on stdout (no stdio serve).
    p.add_argument(
        "--once",
        choices=("resolve", "get_skill", "status"),
        default=None,
        help="FR #7000: one-shot tool call (JSON on stdout) instead of MCP stdio",
    )
    p.add_argument("--seed", default="", help="With --once resolve: job seed (FR/MRB/UAT) or skill id")
    p.add_argument("--path", default="", help="With --once get_skill: SKILL.md path under a --root")
    args = p.parse_args(argv)
    try:
        roots = roots_from_argv(
            [
                *([f"--root={r}" for r in (args.root or [])]),
                *(["--job-worktree", args.job_worktree] if args.job_worktree else []),
                "--max-bytes",
                str(args.max_bytes),
            ]
        )
    except JobSkillsRootRefused as exc:
        print(f"ERROR job-skills-root: {exc}", file=sys.stderr)
        return 2
    server = SkillDagServer(roots=roots, max_bytes=args.max_bytes)
    if args.once:
        if args.once == "resolve":
            result = server.resolve(str(args.seed or ""))
        elif args.once == "get_skill":
            result = server.get_skill(str(args.path or ""))
        else:
            result = server.status()
        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        return 0
    serve_stdio(server, sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
