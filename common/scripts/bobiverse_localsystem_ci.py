"""FR #7103: run recipe pytest suites as Windows LocalSystem (GitHub-hosted CI).

Never logs token values. Never creates GitHub releases or tags.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SUITE_SPECS = (
    {"name": "jeeves", "cmd": "python -m pytest -q -p no:cacheprovider jeeves/tests"},
    {"name": "airc", "cmd": "python -m pytest -q -p no:cacheprovider airc/tests"},
    {"name": "common", "cmd": "python -m pytest -q -p no:cacheprovider common/tests"},
    {"name": "bob", "cmd": "python -m pytest -q -p no:cacheprovider bob/tests"},
)

SMOKE_CMD = (
    "python -m pytest -q -p no:cacheprovider "
    "common/tests/test_fr7103_localsystem_ci.py --tb=line"
)

_SECRET_NAME = re.compile(
    r"(?i)(TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|AUTHORIZATION|CREDENTIAL)"
)
_GHP = re.compile(r"\bghp_[A-Za-z0-9]+\b")
_ASSIGN = re.compile(r"(?i)((?:GH_|GITHUB_)?TOKEN=)\S+")


def child_env(src: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if src is None else src)
    return {k: v for k, v in env.items() if not _SECRET_NAME.search(k)}


def scrub_ci_log(text: str) -> str:
    out = _GHP.sub("REDACTED", text)
    return _ASSIGN.sub(r"\1REDACTED", out)


def is_localsystem_identity(whoami: str, username: str) -> bool:
    w = (whoami or "").strip().lower().replace("/", "\\")
    u = (username or "").strip().upper()
    if u in ("SYSTEM", "LOCAL SYSTEM"):
        return True
    return w.endswith("\\system") or w == "nt authority\\system"


def _whoami() -> str:
    try:
        return subprocess.check_output(["whoami"], text=True, timeout=30).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _run_cmd(cmd: str, cwd: Path, log_path: Path, env: dict[str, str]) -> int:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        shell=True,
        capture_output=True,
        text=True,
        env=env,
    )
    blob = scrub_ci_log((proc.stdout or "") + "\n" + (proc.stderr or ""))
    log_path.write_text(blob, encoding="utf-8")
    return int(proc.returncode)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=("smoke", "full"), default="smoke")
    p.add_argument("--repo-root", required=True)
    p.add_argument("--out-dir", required=True)
    args = p.parse_args(argv)
    root = Path(args.repo_root).resolve()
    out = Path(args.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    env = child_env()
    who = _whoami()
    user = os.environ.get("USERNAME", "")
    ident = {
        "whoami": who,
        "username": user,
        "is_localsystem": is_localsystem_identity(who, user),
    }
    (out / "identity.json").write_text(json.dumps(ident, indent=2) + "\n", encoding="utf-8")
    summary: dict = {"mode": args.mode, "identity": ident, "suites": []}
    rc = 0
    if not ident["is_localsystem"]:
        summary["error"] = "not LocalSystem"
        rc = 2
    else:
        jobs = (
            [{"name": "smoke", "cmd": SMOKE_CMD}]
            if args.mode == "smoke"
            else list(SUITE_SPECS)
        )
        for spec in jobs:
            logp = out / f"suite-{spec['name']}.log"
            code = _run_cmd(spec["cmd"], root, logp, env)
            summary["suites"].append({"name": spec["name"], "rc": code, "log": str(logp)})
            if code != 0:
                rc = code
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    sys.stdout.write(scrub_ci_log(json.dumps(summary) + "\n"))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
