"""Service-owned Priority Web SDK worker (FR #5283).

Lives under the Airc install tree. Not a standalone PriorityClient.exe.
Invocation is only via the Airc Priority module (env AIRC_PRIORITY_OWNED=1
or --from-airc). PRIORITY IRC verbs are a later slice.
"""
from __future__ import annotations

import os
import sys


def owned_by_airc(argv: list[str] | None = None) -> bool:
    args = list(sys.argv[1:] if argv is None else argv)
    if os.environ.get("AIRC_PRIORITY_OWNED", "").strip() == "1":
        return True
    return "--from-airc" in args


def main(argv: list[str] | None = None) -> int:
    if not owned_by_airc(argv):
        sys.stderr.write("refuse: invoke only via Airc Priority module (FR #5283)\n")
        return 2
    sys.stdout.write("ok owned=airc worker=priority-web-sdk\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
