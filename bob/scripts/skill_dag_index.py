"""FR #6860: durable slim skill-dag index builder from SKILL.md (no bodies).

Builds an on-disk index of id / one-line description / depends_on / path / bytes.
Cycle detection exits 1 and leaves any previous index file in place.
Rebuilds when a source SKILL.md mtime is newer than the index.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Reuse frontmatter parser from the stdio MCP module (same package dir on sys.path).
from skill_dag_mcp import _parse_frontmatter


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def is_nested_skill_book(skill: Path, root: Path) -> bool:
    """True when SKILL.md sits under another skill's ``.grok/skills`` copy (FR #6921)."""
    try:
        rel = Path(skill).resolve().relative_to(Path(root).resolve())
    except ValueError:
        return False
    return ".grok" in rel.parts[:-1]


def _relative_depth(skill: Path, root: Path) -> int:
    try:
        return len(Path(skill).resolve().relative_to(Path(root).resolve()).parts)
    except ValueError:
        return 10**9


def read_skill_markdown(path: Path) -> str | None:
    """Read SKILL.md without failing the catalog on one non-UTF-8 file (FR #7193)."""
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return None
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    try:
        return raw.decode("cp1252")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")


def _node_from_skill(skill: Path) -> dict[str, Any] | None:
    text = read_skill_markdown(skill)
    if text is None:
        return None
    meta = _parse_frontmatter(text)
    sid = str(meta.get("name") or skill.parent.name).strip()
    if not sid:
        return None
    return {
        "id": sid,
        "description": str(meta.get("description") or "").strip(),
        "depends_on": list(meta.get("depends_on") or []),
        "path": str(skill.resolve()),
        "bytes": len(text.encode("utf-8")),
    }


def scan_skills_with_collisions(roots: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Index canonical SKILL.md files; skip nested books; report same-root name collisions.

    FR #6921: nested ``.grok/skills`` copies inside a root are skipped.
    FR #7076: the same id in later vision roots (bob / user harvest copies) is
    a duplicate node, not ``status.last_error``. Keep the first configured root
    (worker seat, then bob, then common, then user). Same-root extra paths stay
    collisions.
    """
    by_id: dict[str, list[tuple[int, int, Path, dict[str, Any]]]] = {}
    for root_rank, root in enumerate(roots):
        root = Path(root)
        if not root.is_dir():
            continue
        for skill in sorted(root.rglob("SKILL.md")):
            if not skill.is_file() or is_nested_skill_book(skill, root):
                continue
            try:
                node = _node_from_skill(skill)
            except Exception:
                continue
            if node is None:
                continue
            depth = _relative_depth(skill, root)
            by_id.setdefault(node["id"], []).append(
                (root_rank, depth, skill.resolve(), node)
            )

    nodes: list[dict[str, Any]] = []
    collisions: list[dict[str, Any]] = []
    for sid, group in sorted(by_id.items()):
        uniq_paths: list[tuple[int, int, Path, dict[str, Any]]] = []
        seen_p: set[str] = set()
        for rank, depth, path, node in group:
            key = str(path)
            if key in seen_p:
                continue
            seen_p.add(key)
            uniq_paths.append((rank, depth, path, node))
        uniq_paths.sort(key=lambda item: (item[0], item[1], str(item[2]).lower()))
        nodes.append(uniq_paths[0][3])
        by_rank: dict[int, list[Path]] = {}
        for rank, _d, path, _n in uniq_paths:
            by_rank.setdefault(rank, []).append(path)
        collide_paths: list[str] = []
        for _rank, paths in sorted(by_rank.items()):
            if len(paths) > 1:
                collide_paths.extend(str(p) for p in paths)
        if collide_paths:
            collisions.append({"id": sid, "paths": collide_paths})
    return nodes, collisions


def format_name_collisions(collisions: list[dict[str, Any]]) -> str:
    if not collisions:
        return ""
    parts = []
    for c in collisions:
        paths = "; ".join(c.get("paths") or [])
        parts.append(f"{c.get('id')}: {paths}")
    return "skill_dag_index: name collision " + " | ".join(parts)


def scan_skills(roots: list[Path]) -> list[dict[str, Any]]:
    """Collect one slim node per SKILL.md under the roots. No body text."""
    nodes, collisions = scan_skills_with_collisions(roots)
    msg = format_name_collisions(collisions)
    if msg:
        sys.stderr.write(msg + "\n")
    return nodes


def find_cycle(nodes: list[dict[str, Any]]) -> list[str] | None:
    """Return one cycle path (ids) when the depends_on graph has a cycle, else None."""
    graph = {n["id"]: [str(d) for d in (n.get("depends_on") or [])] for n in nodes}
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {sid: WHITE for sid in graph}
    stack: list[str] = []

    def dfs(sid: str) -> list[str] | None:
        color[sid] = GRAY
        stack.append(sid)
        for dep in graph.get(sid, []):
            if dep not in graph:
                continue
            if color[dep] == GRAY:
                if dep in stack:
                    i = stack.index(dep)
                    return stack[i:] + [dep]
                return [sid, dep, sid]
            if color[dep] == WHITE:
                found = dfs(dep)
                if found:
                    return found
        stack.pop()
        color[sid] = BLACK
        return None

    for sid in graph:
        if color[sid] == WHITE:
            found = dfs(sid)
            if found:
                return found
    return None


def source_mtimes(roots: list[Path]) -> list[float]:
    times: list[float] = []
    for root in roots:
        root = Path(root)
        if not root.is_dir():
            continue
        for skill in root.rglob("SKILL.md"):
            if skill.is_file():
                try:
                    times.append(skill.stat().st_mtime)
                except OSError:
                    continue
    return times


def needs_rebuild(*, index_path: Path, roots: list[Path]) -> bool:
    """True when the index is missing or any SKILL.md mtime is newer than the index."""
    index_path = Path(index_path)
    if not index_path.is_file():
        return True
    try:
        index_mtime = index_path.stat().st_mtime
    except OSError:
        return True
    times = source_mtimes(roots)
    if not times:
        return False
    return max(times) > index_mtime


def load_index(index_path: Path) -> dict[str, Any]:
    data = json.loads(Path(index_path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("index root must be an object")
    nodes = data.get("nodes")
    if not isinstance(nodes, list):
        raise ValueError("index.nodes must be a list")
    return data


def build_index(*, roots: list[Path], index_path: Path, force: bool = False) -> int:
    """Write a slim index. Exit 0 on success. Exit 1 on cycle (prior file left intact)."""
    index_path = Path(index_path)
    roots = [Path(r) for r in roots]

    if not force and index_path.is_file() and not needs_rebuild(index_path=index_path, roots=roots):
        return 0

    nodes, collisions = scan_skills_with_collisions(roots)
    msg = format_name_collisions(collisions)
    if msg:
        sys.stderr.write(msg + "\n")
    cycle = find_cycle(nodes)
    if cycle is not None:
        sys.stderr.write("skill_dag_index: cycle detected: " + " -> ".join(cycle) + "\n")
        return 1

    payload = {
        "built_at": _utc_now(),
        "roots": [str(Path(r).resolve()) for r in roots if Path(r).is_dir()],
        "nodes": nodes,
        "collisions": collisions,
    }
    index_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = index_path.with_suffix(index_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(index_path)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="FR #6860 slim skill-dag index builder")
    p.add_argument("--root", action="append", default=[], help="Skill root to scan (repeatable)")
    p.add_argument("--out", required=True, help="Index JSON output path")
    p.add_argument("--force", action="store_true", help="Rebuild even when index is fresher")
    args = p.parse_args(argv)
    roots = [Path(r) for r in (args.root or [])]
    if not roots:
        here = Path(__file__).resolve()
        pack = here.parents[1] / ".grok" / "skills"
        if pack.is_dir():
            roots = [pack]
        user = Path.home() / ".grok" / "skills"
        if user.is_dir():
            roots.append(user)
    return build_index(roots=roots, index_path=Path(args.out), force=bool(args.force))


if __name__ == "__main__":
    raise SystemExit(main())
