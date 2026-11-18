#!/usr/bin/env python3
"""FR #8157: map changed source files to a bounded in-job pytest selection.

Seat agents must not run full ``jeeves/tests`` / ``common/tests`` trees (OpenCode
600 s tool timeout). Use::

    python common/scripts/select_tests.py --changed
    python common/scripts/select_tests.py --changed --base origin/main
    python -m pytest -q $(python common/scripts/select_tests.py --changed)

CI still runs the full suites on the PR.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_MAX = 50

# High-fanout modules: name-based maps keep the selection under DEFAULT_MAX.
MODULE_NAME_HINTS: dict[str, tuple[str, ...]] = {
    "gitclaim.py": ("gitclaim", "offer_order", "offer-order"),
    "focus_ignore.py": ("offer_order", "offer-order", "focus_ignore", "focus-ignore"),
    "shop_listen.py": ("shop_listen", "shop-listen"),
    "bobreport.py": ("bobreport", "digest"),
    "bob_worker.py": ("bob_worker", "fr6370", "opencode_finish"),
}

# Paths that mean "full suite" when passed alone to pytest (FR #8157 warn).
FULL_SUITE_PATHS = frozenset(
    {
        "jeeves/tests",
        "jeeves\\tests",
        "common/tests",
        "common\\tests",
        "bob/tests",
        "bob\\tests",
        "airc/tests",
        "airc\\tests",
        "tests",
    }
)


def repo_root_from(cwd: Path | None = None) -> Path:
    here = Path(cwd or Path.cwd()).resolve()
    for p in [here, *here.parents]:
        if (p / ".git").exists() and (p / "common" / "scripts").is_dir():
            return p
    return here


def norm_rel(path: str | Path, root: Path) -> str:
    raw = str(path).replace("\\", "/")
    try:
        rel = Path(path).resolve().relative_to(root.resolve())
        return str(rel).replace("\\", "/")
    except Exception:
        return raw.lstrip("./")


def git_changed_files(
    root: Path,
    *,
    base: str = "origin/main",
    run=subprocess.run,
) -> list[str]:
    """Files changed vs ``base`` (committed + unstaged + untracked)."""
    out: list[str] = []
    seen: set[str] = set()

    def _add(blob: str) -> None:
        for line in (blob or "").splitlines():
            rel = line.strip().replace("\\", "/")
            if not rel or rel in seen:
                continue
            seen.add(rel)
            out.append(rel)

    try:
        diff = run(
            ["git", "-C", str(root), "diff", "--name-only", f"{base}...HEAD"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if int(getattr(diff, "returncode", 1)) == 0:
            _add(diff.stdout or "")
        else:
            # Shallow / missing base: fall back to merge-base style against HEAD~ if needed.
            diff2 = run(
                ["git", "-C", str(root), "diff", "--name-only", "HEAD"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            _add(getattr(diff2, "stdout", "") or "")
    except Exception:
        pass
    try:
        unstaged = run(
            ["git", "-C", str(root), "diff", "--name-only"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        _add(getattr(unstaged, "stdout", "") or "")
        untracked = run(
            ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        _add(getattr(untracked, "stdout", "") or "")
    except Exception:
        pass
    return out


def _is_test_path(rel: str) -> bool:
    low = rel.lower().replace("\\", "/")
    name = Path(low).name
    if not name.endswith(".py"):
        return False
    if "/tests/" in f"/{low}" or low.startswith("tests/"):
        return name.startswith("test_") or name.endswith("_test.py")
    return False


def _stem_hints(rel: str) -> list[str]:
    name = Path(rel).name
    stem = Path(name).stem
    hints = [stem.lower()]
    for key, extra in MODULE_NAME_HINTS.items():
        if name.lower() == key.lower() or stem.lower() == Path(key).stem.lower():
            hints.extend(extra)
    # Drop generic stems that match too many files.
    drop = {"__init__", "conftest", "util", "utils", "helpers", "common", "main"}
    return [h for h in hints if h and h not in drop]


def discover_test_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for service in ("jeeves", "common", "bob", "airc"):
        tests = root / service / "tests"
        if tests.is_dir():
            out.extend(sorted(tests.rglob("test_*.py")))
    top = root / "tests"
    if top.is_dir():
        out.extend(sorted(top.rglob("test_*.py")))
    return out


def map_changed_to_tests(
    changed: list[str],
    root: Path,
    *,
    max_files: int = DEFAULT_MAX,
) -> list[str]:
    """Return relative test paths for ``changed`` source/test files."""
    selected: list[str] = []
    seen: set[str] = set()

    def _take(rel: str) -> None:
        r = rel.replace("\\", "/")
        if r in seen:
            return
        path = root / r
        if not path.is_file():
            return
        seen.add(r)
        selected.append(r)

    hints: list[str] = []
    for rel in changed:
        nrel = rel.replace("\\", "/")
        if _is_test_path(nrel):
            _take(nrel)
            continue
        if not nrel.endswith((".py", ".ps1", ".md")):
            continue
        hints.extend(_stem_hints(nrel))

    # Dedupe hints preserving order.
    uniq_hints: list[str] = []
    hseen: set[str] = set()
    for h in hints:
        if h in hseen:
            continue
        hseen.add(h)
        uniq_hints.append(h)

    if uniq_hints:
        for test in discover_test_files(root):
            rel = norm_rel(test, root)
            name = test.name.lower()
            if any(h in name for h in uniq_hints):
                _take(rel)
            if len(selected) >= max_files:
                break

    # Always prefer FR-named new tests already in the changed set (handled above).
    return selected[:max_files]


def looks_like_full_suite_argv(argv: list[str]) -> bool:
    """True when pytest argv targets a whole tests tree without file selection."""
    paths = []
    skip_next = False
    for i, a in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        if a in ("-k", "-m", "--maxfail", "-n", "--timeout", "-o", "-c", "--rootdir", "--basetemp"):
            skip_next = True
            continue
        if a.startswith("-"):
            continue
        if a.endswith(".py") or "::" in a:
            return False
        paths.append(a.replace("\\", "/").rstrip("/"))
    if not paths:
        # bare ``pytest`` / ``pytest -q`` with no path => collection of cwd (often full).
        return True
    for p in paths:
        leaf = p
        if leaf in FULL_SUITE_PATHS or leaf.endswith("/tests") or re.fullmatch(r"(jeeves|common|bob|airc)/tests", leaf):
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="FR #8157 select targeted pytest paths")
    p.add_argument("--changed", action="store_true", help="select from git changes vs --base")
    p.add_argument("--base", default="origin/main", help="git diff base (default origin/main)")
    p.add_argument("--repo-root", default="", help="repo root (default: discover from cwd)")
    p.add_argument("--max", type=int, default=DEFAULT_MAX, help=f"max test files (default {DEFAULT_MAX})")
    p.add_argument("--files", nargs="*", default=[], help="explicit changed files (test fixture)")
    p.add_argument("--print0", action="store_true", help="NUL-separate paths")
    p.add_argument("--check-full-suite", nargs=argparse.REMAINDER, help="exit 2 if argv looks like a full suite")
    args = p.parse_args(argv)

    if args.check_full_suite is not None:
        rest = list(args.check_full_suite)
        if rest and rest[0] == "--":
            rest = rest[1:]
        if looks_like_full_suite_argv(rest):
            print(
                "FR #8157: refusing/warning full-suite pytest in-job. "
                "Use: python common/scripts/select_tests.py --changed "
                "then pytest those paths. CI runs the full suite.",
                file=sys.stderr,
            )
            return 2
        return 0

    root = Path(args.repo_root).resolve() if args.repo_root else repo_root_from()
    if args.files:
        changed = [norm_rel(f, root) for f in args.files]
    elif args.changed:
        changed = git_changed_files(root, base=args.base)
    else:
        p.error("pass --changed and/or --files")
        return 2

    selected = map_changed_to_tests(changed, root, max_files=max(1, int(args.max)))
    if not selected:
        print(
            "# FR #8157: no test files mapped; add test_fr<N>_*.py or pass paths explicitly",
            file=sys.stderr,
        )
        return 1
    sep = "\0" if args.print0 else "\n"
    sys.stdout.write(sep.join(selected) + ("" if args.print0 else "\n"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
