#!/usr/bin/env python3
"""FR #8157: in-job pytest wrapper that rejects full-suite invocations quickly.

Usage::

    python common/scripts/run_job_pytest.py -q path/to/test_fr8157_*.py
    python common/scripts/run_job_pytest.py --changed

Without path selection (``jeeves/tests``, ``common/tests``, bare pytest), exits
immediately with a warning instead of burning the OpenCode 600 s shell budget.
CI still runs the full suites on the PR.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Allow running as a script from any cwd.
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import select_tests as st  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(description="FR #8157 job pytest (targeted only)")
    p.add_argument(
        "--changed",
        action="store_true",
        help="select tests via select_tests.py --changed then run them",
    )
    p.add_argument("--base", default="origin/main")
    p.add_argument("--repo-root", default="")
    p.add_argument("--max", type=int, default=st.DEFAULT_MAX)
    p.add_argument(
        "--allow-full-suite",
        action="store_true",
        help="escape hatch (CI / explicit); still discouraged in seats",
    )
    args, pytest_argv = p.parse_known_args(argv)

    root = Path(args.repo_root).resolve() if args.repo_root else st.repo_root_from()
    if args.changed:
        selected = st.map_changed_to_tests(
            st.git_changed_files(root, base=args.base),
            root,
            max_files=max(1, int(args.max)),
        )
        if not selected:
            print(
                "FR #8157: select_tests --changed mapped nothing; "
                "add test_fr<N>_*.py or pass explicit paths.",
                file=sys.stderr,
            )
            return 1
        pytest_argv = list(pytest_argv) + selected

    if not args.allow_full_suite and st.looks_like_full_suite_argv(pytest_argv):
        print(
            "FR #8157 WARN: full-suite pytest blocked in-job (would hit ~600s tool timeout).\n"
            "  Use targeted paths, e.g.:\n"
            "    python common/scripts/select_tests.py --changed\n"
            "    python common/scripts/run_job_pytest.py --changed\n"
            "    python -m pytest -q bob/tests/test_fr8157_*.py\n"
            "  CI runs the full suite on the PR.",
            file=sys.stderr,
        )
        return 2

    env = os.environ.copy()
    # Prefer job-tree scripts on PYTHONPATH when present.
    for rel in ("bob/scripts", "common/scripts", "jeeves/scripts", "common/tests"):
        d = root / rel.replace("/", os.sep)
        if d.is_dir():
            env["PYTHONPATH"] = str(d) + os.pathsep + env.get("PYTHONPATH", "")

    cmd = [sys.executable, "-m", "pytest", *pytest_argv]
    try:
        return int(subprocess.call(cmd, cwd=str(root), env=env))
    except OSError as e:
        print(f"FR #8157: pytest launch failed: {type(e).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
