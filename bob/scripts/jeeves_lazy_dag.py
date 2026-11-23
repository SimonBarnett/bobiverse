"""FR #8683 / BOB-39: Agents > Jeeves lazy-load skill DAG smoke on J: skills.

Index + depends_on graph only (frontmatter). Do not eagerly load every SKILL.md body.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_SKILLS_ROOT = r"J:\.grok\skills"


def smoke(skills_root: Path | str) -> dict[str, Any]:
    """Slim DAG check: scan nodes (no body dump) and reject cycles."""
    root = Path(skills_root)
    # Import beside this file (bob/scripts on sys.path when run as script).
    here = Path(__file__).resolve().parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    from skill_dag_index import find_cycle, scan_skills

    nodes = scan_skills([root]) if root.is_dir() else []
    cycle = find_cycle(nodes) if nodes else None
    if cycle:
        raise RuntimeError("skill DAG cycle: " + " -> ".join(cycle))
    # Prove lazy: result carries ids/paths/bytes only - never concatenated bodies.
    slim = [{"id": n.get("id"), "path": n.get("path"), "bytes": n.get("bytes")} for n in nodes]
    line = f"jeeves-dag lazy nodes={len(slim)} root={root}"
    return {"mode": "lazy", "nodes": len(slim), "skills": slim, "line": line}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="BOB-39 Jeeves lazy skill-DAG smoke")
    p.add_argument("--skills-root", default=DEFAULT_SKILLS_ROOT)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    try:
        result = smoke(args.skills_root)
    except Exception as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(result["line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
