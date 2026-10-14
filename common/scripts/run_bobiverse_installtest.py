"""FR #4026: drain one INSTALLTEST queue job or run InstallTestRunner from CLI (no agent tokens).

Chair enqueues `home/build-queue/installtest-*.json` on INSTALLTEST v1; this process runs
msiexec + post-checks via `InstallTestRunner` with GitHubFiler or `--fake-filer`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import bobiverse_build as bb  # noqa: E402


def _load_job(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _pick_installtest_job(queue_dir: Path) -> Path | None:
    files = sorted(
        p
        for p in queue_dir.glob("*.json")
        if p.name.startswith("installtest-")
        or (p.is_file() and '"INSTALLTEST"' in p.read_text(encoding="utf-8", errors="ignore"))
    )
    return files[0] if files else None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="FR #4026 bobiverse INSTALLTEST runner")
    p.add_argument("--repo-root", default=".", help="git / install root with .bobiverse/build.yml")
    p.add_argument("--repo", default="", help="owner/repo (default from job or SimonBarnett/bobiverse)")
    p.add_argument("--version", default="")
    p.add_argument("--tag", default="")
    p.add_argument("--job", default="", help="path to installtest queue JSON from chair")
    p.add_argument("--queue-dir", default="", help="drain oldest installtest-*.json from this dir")
    p.add_argument("--evidence-dir", default="", help="default: %ProgramData%/Bobiverse/installtest-evidence/<version>")
    p.add_argument("--fake-filer", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--local-machine", default=os.environ.get("BOB_MACHINE_ID", ""))
    args = p.parse_args(argv)

    job: dict = {}
    job_path: Path | None = None
    if args.job:
        job_path = Path(args.job)
        job = _load_job(job_path)
    elif args.queue_dir:
        q = Path(args.queue_dir)
        job_path = _pick_installtest_job(q)
        if job_path is None:
            print("installtest: queue empty")
            return 0
        job = _load_job(job_path)

    if job.get("kind") and str(job.get("kind")).upper() not in ("INSTALLTEST", "INSTALL-TEST"):
        print(f"installtest: refused job kind={job.get('kind')}", file=sys.stderr)
        return 2

    repo = (args.repo or job.get("repo") or "SimonBarnett/bobiverse").strip()
    version = (args.version or job.get("version") or "").strip()
    tag = (args.tag or job.get("tag") or (f"v{version}" if version else "")).strip()
    if not version:
        print("installtest: need --version or job.version", file=sys.stderr)
        return 2

    root = Path(args.repo_root).resolve()
    recipe = bb.load_recipe(root)
    if not recipe.install_test:
        print("installtest: recipe has no install_test", file=sys.stderr)
        return 2
    target = str((recipe.install_test or {}).get("machine") or recipe.machine)
    local = (args.local_machine or "").strip()
    if local and not bb.is_recipe_build_machine(target, local):
        print(f"installtest: refused machine local={local} recipe={target}")
        return 3

    evidence = (
        Path(args.evidence_dir)
        if args.evidence_dir
        else Path(os.environ.get("ProgramData", "C:/ProgramData"))
        / "Bobiverse"
        / "installtest-evidence"
        / version
    )
    filer = bb.FakeGitHubFiler() if args.fake_filer else bb.GitHubFiler()
    runner = bb.InstallTestRunner(
        repo=repo,
        version=version,
        tag=tag,
        recipe=recipe,
        evidence_dir=evidence,
        filer=filer,
        dry_run=bool(args.dry_run),
    )
    report = runner.run()
    print(
        json.dumps(
            {
                "ok": report.ok,
                "steps": report.steps,
                "blockers": report.blockers_filed,
                "errors": report.errors,
                "announce": report.announce_lines,
                "evidence_dir": report.evidence_dir,
            },
            indent=2,
            default=str,
        )
    )
    if job_path and report.ok:
        try:
            job_path.rename(job_path.with_suffix(".json.done"))
        except Exception:
            pass
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
