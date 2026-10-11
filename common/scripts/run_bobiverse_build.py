"""FR #4025: drain one BUILD queue job or run BuildRunner from CLI (no agent tokens).

Chair enqueues `home/build-queue/*.json` on BUILD v1; this process executes suites/pack/release
via `BuildRunner` with a real GitHubFiler (gh) or FakeGitHubFiler when `--fake-filer`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# scripts dir on path
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import bobiverse_build as bb  # noqa: E402


def _load_job(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="FR #4025 bobiverse BUILD runner")
    p.add_argument("--repo-root", default=".", help="git / install root with .bobiverse/build.yml")
    p.add_argument("--repo", default="", help="owner/repo (default from job or SimonBarnett/bobiverse)")
    p.add_argument("--version", default="")
    p.add_argument("--ref", default="HEAD")
    p.add_argument("--job", default="", help="path to build-queue JSON from chair")
    p.add_argument("--queue-dir", default="", help="drain oldest *.json from this dir")
    p.add_argument("--work-dir", default="", help="default: %ProgramData%/Bobiverse/build-work")
    p.add_argument("--fake-filer", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--local-machine", default=os.environ.get("BOB_MACHINE_ID", ""))
    args = p.parse_args(argv)

    job = {}
    job_path = None
    if args.job:
        job_path = Path(args.job)
        job = _load_job(job_path)
    elif args.queue_dir:
        q = Path(args.queue_dir)
        files = sorted(q.glob("*.json"))
        if not files:
            print("build: queue empty")
            return 0
        job_path = files[0]
        job = _load_job(job_path)

    repo = (args.repo or job.get("repo") or "SimonBarnett/bobiverse").strip()
    # BUILD v1 may list repos=a,b — take first for this worker
    if "," in repo:
        repo = repo.split(",")[0].strip()
    if job.get("repos"):
        repos = job["repos"]
        if isinstance(repos, str):
            repo = repos.split(",")[0].strip()
        elif isinstance(repos, list) and repos:
            repo = str(repos[0]).strip()
    version = (args.version or job.get("version") or "").strip()
    ref = (args.ref or job.get("ref") or "HEAD").strip()
    if not version:
        print("build: need --version or job.version", file=sys.stderr)
        return 2

    root = Path(args.repo_root).resolve()
    recipe = bb.load_recipe(root)
    local = (args.local_machine or "").strip()
    if local and not bb.is_recipe_build_machine(recipe.machine, local):
        print(f"build: refused machine local={local} recipe={recipe.machine}")
        return 3

    work = Path(args.work_dir) if args.work_dir else Path(os.environ.get("ProgramData", "C:/ProgramData")) / "Bobiverse" / "build-work" / version
    log_dir = work / "logs"
    filer = bb.FakeGitHubFiler() if args.fake_filer else bb.GitHubFiler()
    runner = bb.BuildRunner(
        root,
        repo,
        version,
        ref,
        recipe,
        filer,
        work_dir=work,
        log_dir=log_dir,
        local_machine=local or recipe.machine,
    )
    report = runner.run(dry_run=bool(args.dry_run))
    print(json.dumps({
        "ok": report.ok,
        "blockers": getattr(report, "blockers_filed", None) or getattr(report, "blockers", None),
        "pack_ok": report.pack_ok,
        "release_ok": report.release_ok,
        "announce": report.announce_lines,
        "errors": report.errors,
    }, indent=2, default=str))
    if job_path and report.ok:
        try:
            job_path.rename(job_path.with_suffix(".json.done"))
        except Exception:
            pass
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
